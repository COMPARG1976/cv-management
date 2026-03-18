"""
Router /skills — tassonomia skill e autocomplete.
GET /skills/suggest    → suggerimenti skill per autocomplete
GET /skills/categories → lista categorie disponibili
"""
from typing import Optional

from fastapi import APIRouter, Query, Depends

import app.excel_store as store
from app.deps import get_current_user

router = APIRouter()


@router.get("/suggest")
def suggest_skills(
    q: str = Query(..., min_length=1, description="Testo da cercare"),
    category: Optional[str] = Query(None, description="Filtra per categoria HARD|SOFT"),
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
):
    """Autocomplete skill da tutte le risorse nel DB."""
    q_lower = q.lower().strip()
    seen: dict[str, dict] = {}
    for items in store.STORE["skills"].values():
        for s in items:
            name = s.get("skill_name", "")
            cat = s.get("category", "HARD")
            if not name:
                continue
            if category and cat != category:
                continue
            if q_lower in name.lower():
                key = name.lower()
                if key not in seen:
                    seen[key] = {"skill_name": name, "category": cat, "count": 1}
                else:
                    seen[key]["count"] += 1
    suggestions = sorted(seen.values(), key=lambda x: -x["count"])[:limit]
    return {"suggestions": suggestions}


@router.get("/categories")
def list_categories(current_user: dict = Depends(get_current_user)):
    return {"categories": ["HARD", "SOFT"]}


@router.get("/all")
def list_all_skills(
    category: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """Lista tutte le skill distinte presenti nel sistema (per admin/analytics)."""
    seen: dict[str, dict] = {}
    for email, skills in store.STORE["skills"].items():
        for s in skills:
            name = s.get("skill_name", "")
            if not name:
                continue
            if category and s.get("category") != category:
                continue
            key = name.lower()
            if key not in seen:
                seen[key] = {"skill_name": name, "category": s.get("category", "HARD"), "count": 1}
            else:
                seen[key]["count"] += 1
    result = sorted(seen.values(), key=lambda x: (-x["count"], x["skill_name"]))
    return {"skills": result, "total": len(result)}
