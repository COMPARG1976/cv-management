"""
Auth router — login locale, config, Entra ID exchange (Authorization Code Flow).
"""
import secrets
import string

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt as jose_jwt, JWTError
from sqlalchemy.orm import Session

from app.database import get_db, settings
from app.models import User, UserRole
from app.security import verify_password, create_access_token, hash_password
from app.schemas import TokenResponse, AuthConfig, EntraExchangeRequest

router = APIRouter()


# ── Login locale ──────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    login_id = form_data.username.lower()
    user = db.query(User).filter(
        User.is_active == True,
    ).filter(
        (User.email == login_id) | (User.username == login_id)
    ).first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenziali non valide",
        )

    token = create_access_token({"sub": user.email, "role": user.role.value, "full_name": user.full_name})
    return TokenResponse(access_token=token, role=user.role.value, full_name=user.full_name, email=user.email)


# ── Config ────────────────────────────────────────────────────────────────────

@router.get("/config", response_model=AuthConfig)
def auth_config():
    """Espone il provider auth attivo + configurazione Entra per il frontend."""
    return AuthConfig(
        provider=settings.auth_provider,
        entra_enabled=settings.entra_enabled,
        entra_client_id=settings.entra_client_id if settings.entra_enabled else None,
        entra_tenant_id=settings.entra_tenant_id if settings.entra_enabled else None,
        entra_redirect_uri=settings.entra_redirect_uri if settings.entra_enabled else None,
    )


# ── Entra ID — Authorization Code Exchange ────────────────────────────────────

def _generate_temp_password(length: int = 16) -> str:
    """Genera password sicura casuale per utenti creati automaticamente via Entra."""
    alphabet = string.ascii_letters + string.digits + "!@#$"
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.isupper() for c in pwd)
                and any(c.islower() for c in pwd)
                and any(c.isdigit() for c in pwd)
                and any(c in "!@#$" for c in pwd)):
            return pwd


async def _exchange_code_for_token(code: str, redirect_uri: str) -> dict:
    """Scambia il code con Microsoft e restituisce il token response."""
    token_url = (
        f"https://login.microsoftonline.com/{settings.entra_tenant_id}"
        "/oauth2/v2.0/token"
    )
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(token_url, data={
            "client_id":     settings.entra_client_id,
            "client_secret": settings.entra_client_secret,
            "grant_type":    "authorization_code",
            "code":          code,
            "redirect_uri":  redirect_uri,
            "scope":         "openid email profile",
        })
    if resp.status_code != 200:
        detail = resp.json().get("error_description", resp.text)[:200]
        raise HTTPException(502, f"Errore Microsoft token endpoint: {detail}")
    return resp.json()


async def _fetch_jwks() -> dict:
    """Recupera le chiavi pubbliche JWKS di Microsoft."""
    jwks_url = (
        f"https://login.microsoftonline.com/{settings.entra_tenant_id}"
        "/discovery/v2.0/keys"
    )
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(jwks_url)
    if resp.status_code != 200:
        raise HTTPException(502, "Impossibile recuperare JWKS da Microsoft")
    return resp.json()


async def _verify_id_token(id_token: str) -> dict:
    """
    Verifica la firma RS256 dell'id_token usando JWKS Microsoft.
    audience: entra_audience da config oppure client_id di default.
    """
    audience = settings.entra_audience or settings.entra_client_id

    try:
        header = jose_jwt.get_unverified_header(id_token)
    except JWTError as e:
        raise HTTPException(401, f"Token Entra malformato: {e}")

    kid = header.get("kid")
    jwks = await _fetch_jwks()

    key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if not key:
        raise HTTPException(401, f"Chiave pubblica (kid={kid}) non trovata nel JWKS Microsoft")

    try:
        payload = jose_jwt.decode(
            id_token,
            key,
            algorithms=["RS256"],
            audience=audience,
            options={"verify_exp": True, "verify_aud": True},
        )
    except JWTError as e:
        raise HTTPException(401, f"Token Entra non valido: {e}")

    return payload


def _find_or_create_user(claims: dict, db: Session) -> User:
    """
    Trova l'utente per email (da claims Entra).
    Se non esiste lo crea con ruolo USER e password locale casuale (backup).
    """
    email = (claims.get("preferred_username") or claims.get("email") or "").lower()
    if not email:
        raise HTTPException(401, "Entra ID non ha restituito un indirizzo email")

    user = db.query(User).filter(User.email == email, User.is_active == True).first()

    if not user:
        # Auto-provisioning: crea utente con i dati del token Entra
        full_name = claims.get("name") or email.split("@")[0].replace(".", " ").title()
        temp_pwd  = _generate_temp_password()
        user = User(
            email=email,
            full_name=full_name,
            hashed_password=hash_password(temp_pwd),
            role=UserRole.USER,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    return user


@router.post("/entra/exchange", response_model=TokenResponse)
async def entra_exchange(
    payload: EntraExchangeRequest,
    db: Session = Depends(get_db),
):
    """
    Riceve il code da Microsoft (Authorization Code Flow),
    lo scambia con un id_token, verifica firma JWKS RS256,
    trova o crea l'utente nel DB, restituisce JWT interno.
    """
    if not settings.entra_enabled:
        raise HTTPException(400, "Autenticazione Entra ID non configurata sul server")

    # 1. Scambia code -> token con Microsoft (server-to-server con client_secret)
    token_response = await _exchange_code_for_token(payload.code, payload.redirect_uri)
    id_token = token_response.get("id_token")
    if not id_token:
        raise HTTPException(502, "Microsoft non ha restituito un id_token")

    # 2. Verifica firma RS256 + estrai claims
    claims = await _verify_id_token(id_token)

    # 3. Trova o crea utente nel DB
    user = _find_or_create_user(claims, db)

    # 4. Emette JWT interno (stesso formato del login locale)
    internal_token = create_access_token({
        "sub":       user.email,
        "role":      user.role.value,
        "full_name": user.full_name,
        "auth":      "entra",
    })
    return TokenResponse(
        access_token=internal_token,
        role=user.role.value,
        full_name=user.full_name,
        email=user.email,
    )
