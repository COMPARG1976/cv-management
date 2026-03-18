"""
Dependency injection per FastAPI — auth e RBAC.
Usa excel_store invece di SQLAlchemy.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.security import decode_token
import app.excel_store as store

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    claims = decode_token(token)
    email = claims.get("sub")
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token non valido")

    user = store.get_user(email)
    if not user or user.get("is_active","SI").upper() not in ("SI","TRUE","1"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Utente non trovato o disattivato")
    return user


def require_roles(*roles: str):
    def checker(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user.get("role","USER") not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permessi insufficienti")
        return current_user
    return checker
