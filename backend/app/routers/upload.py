"""
Router /upload — Sprint 3 (Excel backend).
POST /cv    : carica file, chiama AI service, calcola diff con STORE, restituisce risultato
POST /apply : applica le modifiche selezionate dall'utente
"""
import json
import os
import uuid
from datetime import datetime, date
from difflib import SequenceMatcher
from typing import Optional, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form

import app.excel_store as store
from app.excel_store import settings
from app.deps import get_current_user

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc"}


# ── String helpers ────────────────────────────────────────────────────────────

def _sim(a: str, b: str) -> float:
    """Fuzzy similarity 0–1 tra due stringhe."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _parse_date(date_str: Optional[str]) -> Optional[date]:
    """Parsa data e normalizza SEMPRE al primo del mese (ignora il giorno)."""
    if not date_str:
        return None
    try:
        s = str(date_str).strip()
        if len(s) == 4 and s.isdigit():
            return date(int(s), 1, 1)
        if len(s) == 7 and "-" in s:
            y, m = s.split("-")
            return date(int(y), int(m), 1)
        if len(s) >= 10:
            parts = s[:10].split("-")
            return date(int(parts[0]), int(parts[1]), 1)
    except Exception:
        pass
    return None


def _date_str(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


# ── Normalizzazione AI data ───────────────────────────────────────────────────

def _normalize_category(raw: str) -> str:
    raw = (raw or "").upper()
    if raw in ("SOFT", "HARD"):
        return raw
    if any(k in raw for k in ("TECN", "TECH", "HARD", "IT")):
        return "HARD"
    return "SOFT"


def _normalize_rating(raw) -> Optional[int]:
    """Converte livello testuale o numerico in rating 1-5."""
    if raw is None:
        return None
    if isinstance(raw, int):
        return max(1, min(5, raw))
    mapping = {
        "base": 2, "beginner": 1, "basic": 2,
        "intermediate": 3, "medio": 3, "buono": 3,
        "advanced": 4, "avanzato": 4, "ottimo": 4,
        "expert": 5, "esperto": 5, "master": 5,
    }
    key = str(raw).lower().strip()
    return mapping.get(key, 3)


def _degree_level(raw: str) -> Optional[str]:
    """Normalizza un titolo di studio in degree_level."""
    raw = (raw or "").lower()
    if any(k in raw for k in ("doctor", "phd", "dottor")):
        return "DOTTORATO"
    if any(k in raw for k in ("master", "magistr", "laurea magistr", "laurea spec", "msc", "mba")):
        return "LAUREA_MAGISTRALE"
    if any(k in raw for k in ("laurea", "bachelor", "triennal", "bsc")):
        return "LAUREA_TRIENNALE"
    if any(k in raw for k in ("diploma", "maturit", "liceo", "istituto")):
        return "DIPLOMA"
    if any(k in raw for k in ("certific", "cours", "corso")):
        return "CORSO"
    return "ALTRO"


# ── Diff engine ───────────────────────────────────────────────────────────────

def compute_diff(email: str, ai: dict) -> dict:
    """
    Confronta i dati AI con il profilo attuale in STORE.
    Restituisce struttura diff pronta per il frontend.
    """
    # ── Profilo scalare ────────────────────────────────────────────────────────
    cv_row = store.STORE["cv_profiles"].get(email, {})
    user_row = store.STORE["users"].get(email, {})

    scalar_fields = [
        "title", "summary", "phone", "linkedin_url",
        "birth_date", "birth_place", "residence_city",
        "first_employment_date", "availability_status",
    ]
    profile_diff = []
    ai_profile = ai.get("profile", {})
    for field in scalar_fields:
        db_val = cv_row.get(field) or user_row.get(field)
        ai_val = ai_profile.get(field)
        if ai_val is not None and ai_val != "" and ai_val != db_val:
            profile_diff.append({
                "field": field,
                "db_value": db_val,
                "ai_value": ai_val,
                "selected": "db",   # default conservativo
            })

    # ── Skills ────────────────────────────────────────────────────────────────
    existing_skills = store.STORE["skills"].get(email, [])
    ai_skills = ai.get("skills", [])
    skill_items = []
    for ai_s in ai_skills:
        name = (ai_s.get("skill_name") or ai_s.get("name") or "").strip()
        if not name:
            continue
        match = next(
            (s for s in existing_skills if _sim(s.get("skill_name", ""), name) >= 0.85),
            None,
        )
        category = _normalize_category(ai_s.get("category", "HARD"))
        rating = _normalize_rating(ai_s.get("rating") or ai_s.get("level"))
        if match:
            changed = (
                match.get("category") != category
                or match.get("rating") != rating
            )
            skill_items.append({
                "status": "changed" if changed else "unchanged",
                "db": match,
                "ai": {"skill_name": name, "category": category, "rating": rating},
                "selected": "db",
            })
        else:
            skill_items.append({
                "status": "new",
                "db": None,
                "ai": {"skill_name": name, "category": category, "rating": rating},
                "selected": "ai",
            })
    # skill solo in DB
    for s in existing_skills:
        if not any(
            it["db"] and it["db"].get("id") == s.get("id") for it in skill_items
        ):
            skill_items.append({
                "status": "db_only",
                "db": s,
                "ai": None,
                "selected": "db",
            })

    # ── Esperienze ────────────────────────────────────────────────────────────
    existing_exp = store.STORE["experiences"].get(email, [])
    ai_exp = ai.get("references", ai.get("experiences", []))
    exp_items = []
    for ai_e in ai_exp:
        company = (ai_e.get("company_name") or ai_e.get("company") or "").strip()
        role = (ai_e.get("role") or "").strip()
        match = next(
            (
                e for e in existing_exp
                if _sim(e.get("company_name", ""), company) >= 0.80
                and _sim(e.get("role", ""), role) >= 0.70
            ),
            None,
        )
        ai_norm = {
            "company_name": company,
            "client_name": ai_e.get("client_name"),
            "role": role,
            "start_date": _date_str(_parse_date(ai_e.get("start_date"))),
            "end_date": _date_str(_parse_date(ai_e.get("end_date"))),
            "is_current": ai_e.get("is_current", False),
            "project_description": ai_e.get("project_description") or ai_e.get("description"),
            "activities": ai_e.get("activities"),
        }
        if match:
            exp_items.append({
                "status": "changed",
                "db": match,
                "ai": ai_norm,
                "selected": "db",
            })
        else:
            exp_items.append({
                "status": "new",
                "db": None,
                "ai": ai_norm,
                "selected": "ai",
            })
    for e in existing_exp:
        if not any(it["db"] and it["db"].get("id") == e.get("id") for it in exp_items):
            exp_items.append({
                "status": "db_only",
                "db": e,
                "ai": None,
                "selected": "db",
            })

    # ── Education ─────────────────────────────────────────────────────────────
    existing_edu = store.STORE["educations"].get(email, [])
    ai_edu = ai.get("educations", [])
    edu_items = []
    for ai_ed in ai_edu:
        inst = (ai_ed.get("institution") or "").strip()
        match = next(
            (e for e in existing_edu if _sim(e.get("institution", ""), inst) >= 0.80),
            None,
        )
        ai_norm = {
            "institution": inst,
            "degree_level": _degree_level(ai_ed.get("degree_level") or ai_ed.get("degree_type") or ""),
            "field_of_study": ai_ed.get("field_of_study"),
            "graduation_year": ai_ed.get("graduation_year"),
            "grade": ai_ed.get("grade"),
            "notes": ai_ed.get("notes"),
        }
        if match:
            edu_items.append({
                "status": "changed",
                "db": match,
                "ai": ai_norm,
                "selected": "db",
            })
        else:
            edu_items.append({
                "status": "new",
                "db": None,
                "ai": ai_norm,
                "selected": "ai",
            })
    for e in existing_edu:
        if not any(it["db"] and it["db"].get("id") == e.get("id") for it in edu_items):
            edu_items.append({
                "status": "db_only",
                "db": e,
                "ai": None,
                "selected": "db",
            })

    # ── Certifications ────────────────────────────────────────────────────────
    existing_certs = store.STORE["certifications"].get(email, [])
    ai_certs = ai.get("certifications", [])
    cert_items = []
    for ai_c in ai_certs:
        name = (ai_c.get("name") or "").strip()
        match = next(
            (c for c in existing_certs if _sim(c.get("name", ""), name) >= 0.80),
            None,
        )
        ai_norm = {
            "name": name,
            "issuing_org": ai_c.get("issuing_org"),
            "cert_code": ai_c.get("cert_code"),
            "year": ai_c.get("year"),
            "notes": ai_c.get("notes"),
        }
        if match:
            cert_items.append({
                "status": "changed",
                "db": match,
                "ai": ai_norm,
                "selected": "db",
            })
        else:
            cert_items.append({
                "status": "new",
                "db": None,
                "ai": ai_norm,
                "selected": "ai",
            })
    for c in existing_certs:
        if not any(it["db"] and it["db"].get("id") == c.get("id") for it in cert_items):
            cert_items.append({
                "status": "db_only",
                "db": c,
                "ai": None,
                "selected": "db",
            })

    # ── Languages ─────────────────────────────────────────────────────────────
    existing_langs = store.STORE["languages"].get(email, [])
    ai_langs = ai.get("languages", [])
    lang_items = []
    for ai_l in ai_langs:
        name = (ai_l.get("language_name") or ai_l.get("language") or "").strip()
        match = next(
            (l for l in existing_langs if _sim(l.get("language_name", ""), name) >= 0.85),
            None,
        )
        ai_norm = {
            "language_name": name,
            "level": ai_l.get("level"),
        }
        if match:
            lang_items.append({
                "status": "changed" if match.get("level") != ai_l.get("level") else "unchanged",
                "db": match,
                "ai": ai_norm,
                "selected": "db",
            })
        else:
            lang_items.append({
                "status": "new",
                "db": None,
                "ai": ai_norm,
                "selected": "ai",
            })
    for l in existing_langs:
        if not any(it["db"] and it["db"].get("id") == l.get("id") for it in lang_items):
            lang_items.append({
                "status": "db_only",
                "db": l,
                "ai": None,
                "selected": "db",
            })

    return {
        "profile": profile_diff,
        "skills": skill_items,
        "references": exp_items,
        "educations": edu_items,
        "certifications": cert_items,
        "languages": lang_items,
    }


# ── Endpoint: upload CV ───────────────────────────────────────────────────────

@router.post("/cv")
async def upload_cv(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Carica un CV (PDF/DOCX), chiama AI service per il parsing, calcola diff."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Tipo file non supportato: {ext}")

    content = await file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(413, f"File troppo grande (max {settings.max_upload_size_mb} MB)")

    # ── Salva file su disco (volume condiviso con ai-services) ─────────────────
    upload_dir = "/app/uploads"
    os.makedirs(upload_dir, exist_ok=True)
    safe_name = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(upload_dir, safe_name)
    with open(file_path, "wb") as f:
        f.write(content)

    # ── Crea record Document nello STORE ──────────────────────────────────────
    email = current_user["email"]
    doc = await store.add_document(email, {
        "original_filename": file.filename,
        "doc_type": "UPLOAD",
        "upload_date": datetime.utcnow().isoformat(),
        "ai_updated": False,
        "tags": [],
    })

    # ── Chiama AI service ──────────────────────────────────────────────────────
    ai_url = settings.ai_service_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            with open(file_path, "rb") as f:
                resp = await client.post(
                    f"{ai_url}/parse",
                    files={"file": (file.filename, f, file.content_type or "application/octet-stream")},
                )
        if resp.status_code != 200:
            raise HTTPException(502, f"AI service errore {resp.status_code}: {resp.text[:200]}")
        ai_data = resp.json()
    except httpx.RequestError as e:
        raise HTTPException(502, f"AI service non raggiungibile: {e}")

    # ── Calcola diff ──────────────────────────────────────────────────────────
    diff = compute_diff(email, ai_data)

    return {
        "document_id": doc["id"],
        "filename": file.filename,
        "diff": diff,
    }


# ── Endpoint: apply diff ──────────────────────────────────────────────────────

@router.post("/apply")
async def apply_diff(
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    """
    Applica le selezioni dell'utente al profilo STORE.
    payload: { document_id, profile: [...], skills: [...], references: [...],
               educations: [...], certifications: [...], languages: [...] }
    Operazione idempotente: skip su duplicati rilevati per fuzzy matching.
    """
    email = current_user["email"]
    changes = {"profile": 0, "skills": 0, "references": 0,
               "educations": 0, "certifications": 0, "languages": 0}

    # ── Profilo scalare ────────────────────────────────────────────────────────
    for item in payload.get("profile", []):
        if item.get("selected") == "ai":
            field = item["field"]
            value = item["ai_value"]
            await store.update_cv_profile(email, {field: value})
            changes["profile"] += 1

    # ── Skills ────────────────────────────────────────────────────────────────
    existing_skills = store.STORE["skills"].get(email, [])
    for item in payload.get("skills", []):
        selected = item.get("selected", "db")
        if selected == "db":
            continue
        ai = item.get("ai") or {}
        db = item.get("db")
        name = ai.get("skill_name", "")
        if not name:
            continue
        # skip se già esiste (fuzzy)
        if any(_sim(s.get("skill_name", ""), name) >= 0.85 for s in existing_skills):
            # update rating/category se "ai" selezionato su item "changed"
            if item.get("status") == "changed" and db:
                await store.update_skill(email, db["id"], {
                    "category": ai.get("category", db.get("category")),
                    "rating": ai.get("rating", db.get("rating")),
                })
                changes["skills"] += 1
            continue
        await store.add_skill(email, {
            "skill_name": name,
            "category": ai.get("category", "HARD"),
            "rating": ai.get("rating"),
        })
        # refresh
        existing_skills = store.STORE["skills"].get(email, [])
        changes["skills"] += 1

    # ── Esperienze ────────────────────────────────────────────────────────────
    existing_exp = store.STORE["experiences"].get(email, [])
    for item in payload.get("references", []):
        selected = item.get("selected", "db")
        if selected == "db":
            continue
        ai = item.get("ai") or {}
        db = item.get("db")
        company = ai.get("company_name", "")
        role = ai.get("role", "")
        if item.get("status") == "changed" and db and selected == "ai":
            await store.update_experience(email, db["id"], ai)
            changes["references"] += 1
        elif item.get("status") == "new":
            if any(
                _sim(e.get("company_name", ""), company) >= 0.80
                and _sim(e.get("role", ""), role) >= 0.70
                for e in existing_exp
            ):
                continue
            await store.add_experience(email, ai)
            existing_exp = store.STORE["experiences"].get(email, [])
            changes["references"] += 1

    # ── Education ─────────────────────────────────────────────────────────────
    existing_edu = store.STORE["educations"].get(email, [])
    for item in payload.get("educations", []):
        selected = item.get("selected", "db")
        if selected == "db":
            continue
        ai = item.get("ai") or {}
        db = item.get("db")
        inst = ai.get("institution", "")
        if item.get("status") == "changed" and db and selected == "ai":
            await store.update_education(email, db["id"], ai)
            changes["educations"] += 1
        elif item.get("status") == "new":
            if any(_sim(e.get("institution", ""), inst) >= 0.80 for e in existing_edu):
                continue
            await store.add_education(email, ai)
            existing_edu = store.STORE["educations"].get(email, [])
            changes["educations"] += 1

    # ── Certifications ────────────────────────────────────────────────────────
    existing_certs = store.STORE["certifications"].get(email, [])
    for item in payload.get("certifications", []):
        selected = item.get("selected", "db")
        if selected == "db":
            continue
        ai = item.get("ai") or {}
        db = item.get("db")
        name = ai.get("name", "")
        if item.get("status") == "changed" and db and selected == "ai":
            await store.update_certification(email, db["id"], ai)
            changes["certifications"] += 1
        elif item.get("status") == "new":
            if any(_sim(c.get("name", ""), name) >= 0.80 for c in existing_certs):
                continue
            await store.add_certification(email, ai)
            existing_certs = store.STORE["certifications"].get(email, [])
            changes["certifications"] += 1

    # ── Languages ─────────────────────────────────────────────────────────────
    existing_langs = store.STORE["languages"].get(email, [])
    for item in payload.get("languages", []):
        selected = item.get("selected", "db")
        if selected == "db":
            continue
        ai = item.get("ai") or {}
        db = item.get("db")
        lang_name = ai.get("language_name", "")
        if item.get("status") == "changed" and db and selected == "ai":
            await store.update_language(email, db["id"], ai)
            changes["languages"] += 1
        elif item.get("status") == "new":
            if any(_sim(l.get("language_name", ""), lang_name) >= 0.85 for l in existing_langs):
                continue
            await store.add_language(email, ai)
            existing_langs = store.STORE["languages"].get(email, [])
            changes["languages"] += 1

    # ── Marca documento come AI-aggiornato ────────────────────────────────────
    doc_id = payload.get("document_id")
    if doc_id:
        await store.update_document(email, doc_id, {"ai_updated": True})

    return {"status": "ok", "changes": changes}


# ── Endpoint: lista documenti utente ──────────────────────────────────────────

@router.get("/documents")
async def list_documents(current_user: dict = Depends(get_current_user)):
    email = current_user["email"]
    docs = store.STORE["documents"].get(email, [])
    return docs


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    current_user: dict = Depends(get_current_user),
):
    email = current_user["email"]
    ok = await store.delete_document(email, doc_id)
    if not ok:
        raise HTTPException(404, "Documento non trovato")
    return {"status": "deleted"}
