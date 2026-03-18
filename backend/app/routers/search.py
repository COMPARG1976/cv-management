"""
Router /search — ricerca risorse.
GET  /api/v1/resources        → lista risorse (public API per IT_RESOURCE_MGMT)
GET  /api/v1/resources/search → ricerca multi-criterio
"""
from typing import Optional, List

from fastapi import APIRouter, Query, Depends

import app.excel_store as store
from app.deps import get_current_user

router = APIRouter()


def _skill_match(user_skills: list, required: List[str]) -> bool:
    """True se almeno una skill richiesta è presente (case-insensitive)."""
    if not required:
        return True
    names = {s.get("skill_name", "").lower() for s in user_skills}
    return any(r.lower() in names for r in required)


def _to_resource_summary(email: str) -> dict:
    user = store.STORE["users"].get(email, {})
    cv = store.STORE["cv_profiles"].get(email, {})
    skills = store.STORE["skills"].get(email, [])
    return {
        "id": user.get("id", email),
        "full_name": user.get("full_name", ""),
        "email": email,
        "username": user.get("username"),
        "bu_mashfrog": user.get("bu_mashfrog"),
        "mashfrog_office": user.get("mashfrog_office"),
        "title": cv.get("title"),
        "availability_status": cv.get("availability_status", "IN_STAFF"),
        "skills": skills,
    }


@router.get("/resources")
def list_resources(
    current_user: dict = Depends(get_current_user),
):
    """Lista tutte le risorse attive con profilo base e competenze."""
    results = []
    for email, user in store.STORE["users"].items():
        if user.get("is_active", "SI").upper() not in ("SI", "TRUE", "1"):
            continue
        results.append(_to_resource_summary(email))
    return {"resources": results, "total": len(results)}


@router.get("/resources/search")
def search_resources(
    skills: Optional[str] = Query(None, description="Skill da cercare (virgola-separated)"),
    availability: Optional[str] = Query(None, description="Filtro availability_status"),
    bu: Optional[str] = Query(None, description="Filtro BU Mashfrog"),
    office: Optional[str] = Query(None, description="Filtro ufficio"),
    q: Optional[str] = Query(None, description="Ricerca libera su nome/email"),
    current_user: dict = Depends(get_current_user),
):
    """Ricerca multi-criterio per risorse. Usato anche da IT_RESOURCE_MGMT."""
    required_skills = [s.strip() for s in skills.split(",")] if skills else []
    results = []

    for email, user in store.STORE["users"].items():
        if user.get("is_active", "SI").upper() not in ("SI", "TRUE", "1"):
            continue
        cv = store.STORE["cv_profiles"].get(email, {})
        user_skills = store.STORE["skills"].get(email, [])

        # filtro skill
        if required_skills and not _skill_match(user_skills, required_skills):
            continue
        # filtro availability
        if availability and cv.get("availability_status") != availability:
            continue
        # filtro BU
        if bu and (user.get("bu_mashfrog") or "").lower() != bu.lower():
            continue
        # filtro ufficio
        if office and (user.get("mashfrog_office") or "").lower() != office.lower():
            continue
        # ricerca libera su nome/email
        if q:
            q_lower = q.lower()
            name = (user.get("full_name") or "").lower()
            em = email.lower()
            if q_lower not in name and q_lower not in em:
                continue

        results.append(_to_resource_summary(email))

    return {"resources": results, "total": len(results)}
