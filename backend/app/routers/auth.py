"""
Auth router — login locale, config, Entra ID exchange.
Aggiunge: backup giornaliero Excel al primo login di ogni giornata.
"""
import secrets
import string

import httpx
from fastapi import APIRouter, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi import Depends
from jose import jwt as jose_jwt, JWTError

import app.excel_store as store
from app.excel_store import settings
from app.security import verify_password, create_access_token, hash_password
from app.schemas import TokenResponse, AuthConfig, EntraExchangeRequest

router = APIRouter()


# ── Login locale ──────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    login_id = form_data.username.lower().strip()

    # Cerca per email o username
    user = store.get_user(login_id) or store.get_user_by_username(login_id)

    if not user or user.get("is_active", "SI").upper() not in ("SI", "TRUE", "1"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenziali non valide")

    if not verify_password(form_data.password, user.get("hashed_password", "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenziali non valide")

    # Backup giornaliero: controlla e aggiorna se necessario (non bloccante)
    try:
        await store.do_daily_backup()
    except Exception as e:
        print(f"[Backup] Errore non bloccante: {e}")

    token = create_access_token({
        "sub": user["email"],
        "role": user.get("role", "USER"),
        "full_name": user.get("full_name", ""),
    })
    return TokenResponse(
        access_token=token,
        role=user.get("role", "USER"),
        full_name=user.get("full_name", ""),
        email=user["email"],
    )


# ── Config ────────────────────────────────────────────────────────────────────

@router.get("/config", response_model=AuthConfig)
def auth_config():
    return AuthConfig(
        provider=settings.auth_provider,
        entra_enabled=settings.entra_enabled,
        entra_client_id=settings.entra_client_id if settings.entra_enabled else None,
        entra_tenant_id=settings.entra_tenant_id if settings.entra_enabled else None,
        entra_redirect_uri=settings.entra_redirect_uri if settings.entra_enabled else None,
    )


# ── Entra ID — Authorization Code Exchange ────────────────────────────────────

def _generate_temp_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$"
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.isupper() for c in pwd) and any(c.islower() for c in pwd)
                and any(c.isdigit() for c in pwd) and any(c in "!@#$" for c in pwd)):
            return pwd


async def _exchange_code_for_token(code: str, redirect_uri: str) -> dict:
    token_url = (f"https://login.microsoftonline.com/{settings.entra_tenant_id}"
                 "/oauth2/v2.0/token")
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(token_url, data={
            "client_id": settings.entra_client_id,
            "client_secret": settings.entra_client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "scope": "openid email profile",
        })
    if resp.status_code != 200:
        detail = resp.json().get("error_description", resp.text)[:200]
        raise HTTPException(502, f"Errore Microsoft token endpoint: {detail}")
    return resp.json()


async def _fetch_jwks() -> dict:
    jwks_url = (f"https://login.microsoftonline.com/{settings.entra_tenant_id}"
                "/discovery/v2.0/keys")
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(jwks_url)
    if resp.status_code != 200:
        raise HTTPException(502, "Impossibile recuperare JWKS da Microsoft")
    return resp.json()


async def _verify_id_token(id_token: str) -> dict:
    try:
        header = jose_jwt.get_unverified_header(id_token)
    except JWTError as e:
        raise HTTPException(401, f"Token Entra malformato: {e}")

    kid = header.get("kid")
    jwks = await _fetch_jwks()
    key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if not key:
        raise HTTPException(401, f"Chiave pubblica (kid={kid}) non trovata nel JWKS Microsoft")

    audiences_to_try = [settings.entra_client_id]
    if settings.entra_audience and settings.entra_audience != settings.entra_client_id:
        audiences_to_try.append(settings.entra_audience)

    last_error = ""
    for aud in audiences_to_try:
        try:
            return jose_jwt.decode(id_token, key, algorithms=["RS256"], audience=aud,
                                   options={"verify_exp": True, "verify_aud": True})
        except JWTError as e:
            last_error = str(e)
    raise HTTPException(401, f"Token Entra non valido: {last_error}")


async def _find_or_create_user(claims: dict) -> dict:
    email = (claims.get("preferred_username") or claims.get("email") or "").lower()
    if not email:
        raise HTTPException(401, "Entra ID non ha restituito un indirizzo email")

    user = store.get_user(email)
    if not user:
        full_name = claims.get("name") or email.split("@")[0].replace(".", " ").title()
        temp_pwd = _generate_temp_password()
        user = await store.create_user({
            "email": email,
            "full_name": full_name,
            "hashed_password": hash_password(temp_pwd),
            "role": "USER",
        })
    return user


@router.post("/entra/exchange", response_model=TokenResponse)
async def entra_exchange(payload: EntraExchangeRequest):
    if not settings.entra_enabled:
        raise HTTPException(400, "Autenticazione Entra ID non configurata sul server")

    token_response = await _exchange_code_for_token(payload.code, payload.redirect_uri)
    id_token = token_response.get("id_token")
    if not id_token:
        raise HTTPException(502, "Microsoft non ha restituito un id_token")

    claims = await _verify_id_token(id_token)
    user = await _find_or_create_user(claims)

    # Backup giornaliero
    try:
        await store.do_daily_backup()
    except Exception as e:
        print(f"[Backup] Errore non bloccante: {e}")

    internal_token = create_access_token({
        "sub": user["email"],
        "role": user.get("role", "USER"),
        "full_name": user.get("full_name", ""),
        "auth": "entra",
    })
    return TokenResponse(
        access_token=internal_token,
        role=user.get("role", "USER"),
        full_name=user.get("full_name", ""),
        email=user["email"],
    )
