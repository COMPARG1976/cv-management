"""
Router /users — gestione utenti (ADMIN only).
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status

import app.excel_store as store
from app.deps import get_current_user, require_roles
from app.schemas import UserCreate, UserUpdate, UserResponse
from app.security import hash_password

router = APIRouter()


def _to_response(u: dict) -> UserResponse:
    return UserResponse(
        id=u.get("id", ""),
        email=u.get("email", ""),
        full_name=u.get("full_name", ""),
        role=u.get("role", "USER"),
        username=u.get("username") or None,
        bu_mashfrog=u.get("bu_mashfrog") or None,
        mashfrog_office=u.get("mashfrog_office") or None,
        hire_date=u.get("hire_date") or None,
        is_active=u.get("is_active", "SI").upper() in ("SI", "TRUE", "1"),
        created_at=u.get("created_at") or None,
    )


@router.get("", response_model=List[UserResponse])
def list_users(_: dict = Depends(require_roles("ADMIN"))):
    return [_to_response(u) for u in store.list_users()]


@router.get("/{email}", response_model=UserResponse)
def get_user(email: str, _: dict = Depends(require_roles("ADMIN"))):
    u = store.get_user(email)
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utente non trovato")
    return _to_response(u)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(data: UserCreate, _: dict = Depends(require_roles("ADMIN"))):
    if store.get_user(data.email):
        raise HTTPException(400, f"Utente {data.email} già esistente")
    u = await store.create_user({
        "email": data.email,
        "full_name": data.full_name,
        "username": data.username or data.email.split("@")[0],
        "hashed_password": hash_password(data.password),
        "role": data.role or "USER",
        "bu_mashfrog": data.bu_mashfrog or "",
        "mashfrog_office": data.mashfrog_office or "",
        "hire_date": str(data.hire_date_mashfrog) if data.hire_date_mashfrog else "",
    })
    return _to_response(u)


@router.put("/{email}", response_model=UserResponse)
async def update_user(
    email: str,
    data: UserUpdate,
    current_user: dict = Depends(get_current_user),
):
    # Admin può modificare chiunque; utente può modificare solo se stesso
    if current_user.get("role") != "ADMIN" and current_user.get("email") != email:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Permessi insufficienti")

    u = store.get_user(email)
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utente non trovato")

    updates = {}
    if data.full_name is not None:
        updates["full_name"] = data.full_name
    if data.role is not None and current_user.get("role") == "ADMIN":
        updates["role"] = data.role
    if data.is_active is not None and current_user.get("role") == "ADMIN":
        updates["is_active"] = "SI" if data.is_active else "NO"
    if data.bu_mashfrog is not None:
        updates["bu_mashfrog"] = data.bu_mashfrog
    if data.mashfrog_office is not None:
        updates["mashfrog_office"] = data.mashfrog_office
    if data.hire_date_mashfrog is not None:
        updates["hire_date"] = str(data.hire_date_mashfrog)
    if data.password is not None:
        updates["hashed_password"] = hash_password(data.password)

    u = await store.update_user(email, updates)
    return _to_response(u)


@router.delete("/{email}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(email: str, _: dict = Depends(require_roles("ADMIN"))):
    if not store.get_user(email):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Utente non trovato")
    await store.delete_user(email)
