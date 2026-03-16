"""
Auth router — login, config, (futuro) Entra ID exchange.
Pattern identico a IT_RESOURCE_MGMT.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db, settings
from app.models import User
from app.security import verify_password, create_access_token
from app.schemas import TokenResponse, AuthConfig

router = APIRouter()


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


@router.get("/config", response_model=AuthConfig)
def auth_config():
    """Espone il provider auth attivo per configurare il frontend."""
    return AuthConfig(provider=settings.auth_provider)


# ── Entra ID (placeholder per futura integrazione) ────────────────────────────
@router.post("/entra/exchange", response_model=TokenResponse)
def entra_exchange(payload: dict, db: Session = Depends(get_db)):
    """
    Riceve un id_token da Microsoft Entra ID e restituisce un JWT interno.
    TODO Sprint 6: implementare verifica firma con cryptography + JWKS endpoint.
    """
    if settings.auth_provider != "entra":
        raise HTTPException(status_code=400, detail="Entra ID non abilitato")
    raise HTTPException(status_code=501, detail="Entra ID exchange non ancora implementato")
