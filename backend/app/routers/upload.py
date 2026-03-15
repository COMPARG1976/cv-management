"""
Router /upload — Sprint 3.
POST /cv    : carica file, chiama AI service, calcola diff con DB, restituisce risultato
POST /apply : applica le modifiche selezionate dall'utente
"""
import os
import uuid
from datetime import datetime, date
from difflib import SequenceMatcher
from typing import Optional, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.database import get_db, settings
from app.deps import get_current_user
from app.models import (
    User, CV, CVDocument, CVSkill, Reference, Education,
    Certification, Language, SkillCategory, LanguageLevel, DocAttachmentType, DegreeLevel,
)

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc"}


# ── String helpers ────────────────────────────────────────────────────────────

def _sim(a: str, b: str) -> float:
    """Fuzzy similarity 0–1 tra due stringhe."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _parse_date(date_str: Optional[str]) -> Optional[date]:
    """Parsa data e normalizza SEMPRE al primo del mese (ignora il giorno).
    Esempi: "2020-01-15" -> date(2020,1,1) | "2020-01" -> date(2020,1,1) | "2020" -> date(2020,1,1)
    """
    if not date_str:
        return None
    try:
        s = str(date_str).strip()
        if len(s) == 4 and s.isdigit():
            return date(int(s), 1, 1)
        if len(s) == 7 and "-" in s:
            y, m = s.split("-")
            return date(int(y), int(m), 1)
        # Data completa: prendi solo anno+mese
        d = date.fromisoformat(s[:10])
        return date(d.year, d.month, 1)
    except (ValueError, IndexError):
        return None


def _ym(date_str: Optional[str]) -> Optional[str]:
    """Normalizza data a stringa YYYY-MM per confronto (ignora il giorno).
    Il giorno è sempre 1 in DB (normalizzato da _parse_date), ma l'AI
    restituisce 'YYYY-MM' senza giorno -> i due formati sono diversi stringa
    ma uguali nel senso mese/anno.
    """
    d = _parse_date(date_str)
    if d is None:
        return None
    return f"{d.year}-{d.month:02d}"


# ── Field-level diff ──────────────────────────────────────────────────────────

def _field_diff(label: str, field: str, db_val: Any, ai_val: Any) -> dict:
    db_s = str(db_val).strip() if db_val is not None else None
    ai_s = str(ai_val).strip() if ai_val is not None else None
    if db_s is None and ai_s is None:
        status = "unchanged"
    elif db_s is None and ai_s is not None:
        status = "new_ai"
    elif db_s is not None and ai_s is None:
        status = "db_only"
    elif db_s != ai_s:
        status = "changed"
    else:
        status = "unchanged"
    return {"field": field, "label": label, "db_value": db_val, "ai_value": ai_val, "status": status}


def _section(items: list, ai_raw: list) -> dict:
    confs = [x.get("confidence", 0.0) for x in ai_raw if isinstance(x, dict)]
    avg_conf = round(sum(confs) / len(confs), 2) if confs else 0.0
    return {
        "confidence": avg_conf,
        "items": items,
        "count_new":       sum(1 for i in items if i.get("status") == "new"),
        "count_changed":   sum(1 for i in items if i.get("status") == "changed"),
        "count_unchanged": sum(1 for i in items if i.get("status") == "unchanged"),
        "count_db_only":   sum(1 for i in items if i.get("status") == "db_only"),
    }


# ── AI field mapping ──────────────────────────────────────────────────────────

def _map_level(level: Optional[str]) -> Optional[int]:
    """AI level (BASE/INTERMEDIO/AVANZATO/ESPERTO) → DB rating 1-5."""
    return {"BASE": 1, "INTERMEDIO": 3, "AVANZATO": 4, "ESPERTO": 5}.get((level or "").upper())


def _map_category(category: Optional[str]) -> str:
    """AI category → DB SkillCategory.
    TECNICA / HARD / TECHNICAL / TECH → HARD
    LINGUISTICA / SOFT / COMUNICAZIONE → SOFT
    """
    cat = (category or "").upper().strip()
    HARD_KW = {"TECNICA", "TECHNICAL", "TECH", "HARD", "CERTIFICAZIONE",
               "INFORMATICA", "IT", "BACKEND", "FRONTEND", "FRAMEWORK"}
    if any(kw in cat for kw in HARD_KW):
        return "HARD"
    return "SOFT"


# ── Diff computation ──────────────────────────────────────────────────────────

def compute_diff(cv: CV, ai: dict) -> dict:
    """Confronta i dati AI estratti con i dati esistenti nel DB e restituisce il diff."""

    prof = ai.get("profile", {})

    # ── Profilo ──
    profile_diffs = [
        _field_diff("Titolo professionale", "title",          cv.title,          prof.get("title")),
        _field_diff("Sommario / Bio",        "summary",        cv.summary,        prof.get("summary")),
        _field_diff("Telefono",              "phone",          cv.phone,          prof.get("phone")),
        _field_diff("LinkedIn",              "linkedin_url",   cv.linkedin_url,   prof.get("linkedin")),
        _field_diff("Citta di residenza",    "residence_city", cv.residence_city, prof.get("location")),
    ]

    # ── Competenze ──
    db_skills   = list(cv.skills or [])
    ai_skills   = ai.get("skills", [])
    skills_items: list = []
    matched_sk:  set   = set()

    for ai_sk in ai_skills:
        ai_name = (ai_sk.get("name") or "").strip()
        # Match: exact → fuzzy
        db_sk = next((s for s in db_skills if s.skill_name.lower() == ai_name.lower()), None)
        if db_sk is None:
            db_sk = next((s for s in db_skills if _sim(s.skill_name, ai_name) > 0.85), None)

        ai_rating = _map_level(ai_sk.get("level"))
        ai_cat    = _map_category(ai_sk.get("category"))
        ai_label  = (ai_sk.get("level") or "").upper()

        if db_sk is None:
            skills_items.append({
                "status": "new",
                "ai_data": {
                    "skill_name": ai_name, "category": ai_cat,
                    "rating": ai_rating,   "level_label": ai_label,
                    "years_experience": ai_sk.get("years_experience"),
                },
                "confidence": ai_sk.get("confidence", 0.0),
            })
        else:
            matched_sk.add(db_sk.id)
            fds = [
                _field_diff("Livello",   "rating",   db_sk.rating,
                            ai_rating),
                _field_diff("Categoria", "category",
                            db_sk.category.value if db_sk.category else None, ai_cat),
            ]
            changed = any(f["status"] not in ("unchanged", "db_only") for f in fds)
            db_label = {1: "BASE", 2: "BASE", 3: "INTERMEDIO", 4: "AVANZATO", 5: "ESPERTO"}.get(db_sk.rating, "")
            skills_items.append({
                "status": "changed" if changed else "unchanged",
                "db_id":   db_sk.id,
                "db_data": {"skill_name": db_sk.skill_name,
                            "category":   db_sk.category.value if db_sk.category else None,
                            "rating":     db_sk.rating, "level_label": db_label},
                "ai_data": {"skill_name": ai_name, "category": ai_cat,
                            "rating": ai_rating, "level_label": ai_label,
                            "years_experience": ai_sk.get("years_experience")},
                "field_diffs": fds,
                "confidence": ai_sk.get("confidence", 0.0),
            })

    for db_sk in db_skills:
        if db_sk.id not in matched_sk:
            skills_items.append({
                "status": "db_only", "db_id": db_sk.id,
                "db_data": {"skill_name": db_sk.skill_name,
                            "category": db_sk.category.value if db_sk.category else None},
            })

    # ── Esperienze (AI) → Referenze (DB) ──
    db_refs  = list(cv.references or [])
    ai_exps  = ai.get("experiences", [])
    refs_items: list = []
    matched_ref: set = set()

    for ai_exp in ai_exps:
        best_ref, best_score = None, 0.0
        for ref in db_refs:
            c = _sim(ref.company_name or "", ai_exp.get("company", ""))
            r = _sim(ref.role or "",         ai_exp.get("role", ""))
            score = c * 0.5 + r * 0.3
            ai_yr = (ai_exp.get("start_date") or "")[:4]
            if ai_yr and ref.start_date and ai_yr == str(ref.start_date.year):
                score += 0.2
            if score > best_score and score > 0.45:
                best_score, best_ref = score, ref

        ai_ref = {
            "company_name":       ai_exp.get("company"),
            "client_name":        None,
            "role":               ai_exp.get("role"),
            "start_date":         ai_exp.get("start_date"),
            "end_date":           ai_exp.get("end_date"),
            "is_current":         ai_exp.get("is_current", False),
            "project_description":ai_exp.get("description"),
            "activities":         None,
            "skills_acquired":    ai_exp.get("skills_used", []),
        }
        if best_ref is None:
            refs_items.append({"status": "new", "ai_data": ai_ref, "confidence": ai_exp.get("confidence", 0.0)})
        else:
            matched_ref.add(best_ref.id)
            db_start = str(best_ref.start_date) if best_ref.start_date else None
            db_end   = str(best_ref.end_date)   if best_ref.end_date   else None
            db_ref_d = {
                "company_name": best_ref.company_name,
                "role":         best_ref.role,
                "start_date":   db_start,
                "end_date":     db_end,
                "is_current":   best_ref.is_current,
                "project_description": best_ref.project_description,
                "skills_acquired": best_ref.skills_acquired or [],
            }
            fds = [
                _field_diff("Azienda",       "company_name",        best_ref.company_name,         ai_exp.get("company")),
                _field_diff("Ruolo",          "role",               best_ref.role,                  ai_exp.get("role")),
                # Confronto solo YYYY-MM: DB salva "YYYY-MM-01", AI restituisce "YYYY-MM"
                _field_diff("Data inizio",    "start_date",         _ym(db_start),                  _ym(ai_exp.get("start_date"))),
                _field_diff("Data fine",      "end_date",           _ym(db_end),                    _ym(ai_exp.get("end_date"))),
                _field_diff("Corrente",       "is_current",         best_ref.is_current,            ai_exp.get("is_current", False)),
                _field_diff("Descrizione",    "project_description",best_ref.project_description,   ai_exp.get("description")),
                _field_diff("Tecnologie",     "skills_acquired",
                            ", ".join(best_ref.skills_acquired or []) or None,
                            ", ".join(ai_exp.get("skills_used", [])) or None),
            ]
            changed = any(f["status"] not in ("unchanged", "db_only") for f in fds)
            refs_items.append({
                "status": "changed" if changed else "unchanged",
                "db_id": best_ref.id, "db_data": db_ref_d, "ai_data": ai_ref,
                "field_diffs": fds,
                "confidence": ai_exp.get("confidence", 0.0),
            })

    for ref in db_refs:
        if ref.id not in matched_ref:
            refs_items.append({
                "status": "db_only", "db_id": ref.id,
                "db_data": {"company_name": ref.company_name, "role": ref.role,
                            "start_date": str(ref.start_date) if ref.start_date else None},
            })

    # ── Formazione ──
    db_edus  = list(cv.educations or [])
    ai_edus  = ai.get("educations", [])
    edus_items: list = []
    matched_edu: set = set()

    for ai_edu in ai_edus:
        best_edu, best_score = None, 0.0
        for edu in db_edus:
            score = _sim(edu.institution, ai_edu.get("institution", ""))
            if (ai_edu.get("graduation_year") and edu.graduation_year
                    and int(ai_edu["graduation_year"]) == edu.graduation_year):
                score += 0.3
            if score > best_score and score > 0.5:
                best_score, best_edu = score, edu

        ai_edu_d = {
            "institution":    ai_edu.get("institution"),
            "degree_type_raw":ai_edu.get("degree_type"),
            "field_of_study": ai_edu.get("field_of_study"),
            "graduation_year":ai_edu.get("graduation_year"),
            "grade":          ai_edu.get("grade"),
        }
        if best_edu is None:
            edus_items.append({"status": "new", "ai_data": ai_edu_d, "confidence": ai_edu.get("confidence", 0.0)})
        else:
            matched_edu.add(best_edu.id)
            fds = [
                _field_diff("Istituto",     "institution",    best_edu.institution,    ai_edu.get("institution")),
                _field_diff("Campo studio", "field_of_study", best_edu.field_of_study, ai_edu.get("field_of_study")),
                _field_diff("Anno",         "graduation_year",best_edu.graduation_year,ai_edu.get("graduation_year")),
                _field_diff("Voto",         "grade",          best_edu.grade,          ai_edu.get("grade")),
            ]
            changed = any(f["status"] not in ("unchanged", "db_only") for f in fds)
            edus_items.append({
                "status": "changed" if changed else "unchanged",
                "db_id": best_edu.id,
                "db_data": {"institution": best_edu.institution,
                            "field_of_study": best_edu.field_of_study,
                            "graduation_year": best_edu.graduation_year, "grade": best_edu.grade},
                "ai_data": ai_edu_d,
                "field_diffs": fds,
                "confidence": ai_edu.get("confidence", 0.0),
            })

    for edu in db_edus:
        if edu.id not in matched_edu:
            edus_items.append({
                "status": "db_only", "db_id": edu.id,
                "db_data": {"institution": edu.institution, "graduation_year": edu.graduation_year},
            })

    # ── Certificazioni ──
    db_certs  = list(cv.certifications or [])
    ai_certs  = ai.get("certifications", [])
    certs_items: list = []
    matched_cert: set = set()

    for ai_cert in ai_certs:
        best_cert = max(db_certs, key=lambda c: _sim(c.name, ai_cert.get("name", "")), default=None)
        if best_cert and _sim(best_cert.name, ai_cert.get("name", "")) < 0.7:
            best_cert = None
        ai_year = None
        try:
            ai_year = int(str(ai_cert.get("issue_date") or "")[:4]) if ai_cert.get("issue_date") else None
        except (ValueError, TypeError):
            pass
        ai_cert_d = {
            "name":        ai_cert.get("name"),
            "issuing_org": ai_cert.get("issuing_org"),
            "year":        ai_year,
            "expiry_date": ai_cert.get("expiry_date"),
            "doc_url":     ai_cert.get("credential_url"),
        }
        if best_cert is None:
            certs_items.append({"status": "new", "ai_data": ai_cert_d, "confidence": ai_cert.get("confidence", 0.0)})
        else:
            matched_cert.add(best_cert.id)
            fds = [
                _field_diff("Nome",     "name",        best_cert.name,                                          ai_cert.get("name")),
                _field_diff("Ente",     "issuing_org", best_cert.issuing_org,                                   ai_cert.get("issuing_org")),
                _field_diff("Anno",     "year",        best_cert.year,                                          ai_year),
                _field_diff("Scadenza", "expiry_date",
                            str(best_cert.expiry_date) if best_cert.expiry_date else None,
                            ai_cert.get("expiry_date")),
            ]
            changed = any(f["status"] not in ("unchanged", "db_only") for f in fds)
            certs_items.append({
                "status": "changed" if changed else "unchanged",
                "db_id": best_cert.id,
                "db_data": {"name": best_cert.name, "issuing_org": best_cert.issuing_org, "year": best_cert.year},
                "ai_data": ai_cert_d,
                "field_diffs": fds,
                "confidence": ai_cert.get("confidence", 0.0),
            })

    for cert in db_certs:
        if cert.id not in matched_cert:
            certs_items.append({"status": "db_only", "db_id": cert.id, "db_data": {"name": cert.name}})

    # ── Lingue ──
    db_langs  = list(cv.languages or [])
    ai_langs  = ai.get("languages", [])
    langs_items: list = []
    matched_lang: set = set()

    for ai_lang in ai_langs:
        ai_name  = (ai_lang.get("language_name") or "").strip()
        ai_level = (ai_lang.get("level") or "").upper()
        db_lang  = next((l for l in db_langs if l.language_name.lower() == ai_name.lower()), None)
        if db_lang is None:
            db_lang = next((l for l in db_langs if _sim(l.language_name, ai_name) > 0.85), None)

        if db_lang is None:
            langs_items.append({"status": "new", "ai_data": {"language_name": ai_name, "level": ai_level},
                                "confidence": ai_lang.get("confidence", 0.0)})
        else:
            matched_lang.add(db_lang.id)
            db_level = db_lang.level.value if db_lang.level else None
            fd = _field_diff("Livello", "level", db_level, ai_level)
            langs_items.append({
                "status": "changed" if fd["status"] not in ("unchanged",) else "unchanged",
                "db_id":   db_lang.id,
                "db_data": {"language_name": db_lang.language_name, "level": db_level},
                "ai_data": {"language_name": ai_name, "level": ai_level},
                "field_diffs": [fd],
                "confidence": ai_lang.get("confidence", 0.0),
            })

    for lang in db_langs:
        if lang.id not in matched_lang:
            langs_items.append({"status": "db_only", "db_id": lang.id,
                                "db_data": {"language_name": lang.language_name}})

    return {
        "parse_status":       "done",
        "overall_confidence": round(ai.get("confidence", 0.0), 2),
        "profile":            {"confidence": round(prof.get("confidence", 0.0), 2),
                               "field_diffs": profile_diffs},
        "skills":             _section(skills_items,  ai_skills),
        "references":         _section(refs_items,    ai_exps),
        "educations":         _section(edus_items,    ai_edus),
        "certifications":     _section(certs_items,   ai_certs),
        "languages":          _section(langs_items,   ai_langs),
    }


# ── Endpoint: Upload CV ───────────────────────────────────────────────────────

@router.post("/cv")
async def upload_cv(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Carica file CV (PDF/DOCX), chiama AI service, calcola diff con i dati nel DB.
    Restituisce il diff completo pronto per la revisione dell'utente.
    """
    # Validate extension
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Formato non supportato: {ext}. Usa PDF o DOCX.")

    content = await file.read()
    if len(content) > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(400, f"File troppo grande (max {settings.max_upload_size_mb} MB).")

    # Save file to shared volume
    os.makedirs(settings.upload_dir, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}{ext}"
    file_path  = os.path.join(settings.upload_dir, safe_name)
    with open(file_path, "wb") as fh:
        fh.write(content)

    # Get or create CV
    cv = db.query(CV).filter(CV.user_id == current_user.id).first()
    if not cv:
        cv = CV(user_id=current_user.id)
        db.add(cv)
        db.flush()

    # Create CVDocument record
    doc = CVDocument(
        cv_id=cv.id,
        original_filename=file.filename or safe_name,
        mime_type=file.content_type or "application/octet-stream",
        file_size_bytes=len(content),
        parse_status="processing",
        uploaded_by_id=current_user.id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Call AI service (synchronous wait, up to 120s)
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{settings.ai_service_url}/parse",
                json={"file_path": file_path, "document_id": doc.id},
            )
            resp.raise_for_status()
            ai_result = resp.json()
    except Exception as exc:
        doc.parse_status = "error"
        db.commit()
        raise HTTPException(502, f"Errore servizio AI: {exc}")

    if ai_result.get("status") != "ok" or not ai_result.get("data"):
        doc.parse_status = "error"
        db.commit()
        raise HTTPException(422, ai_result.get("error", "Parsing fallito"))

    # Persist AI output
    doc.ai_raw_output = ai_result["data"]
    doc.parse_status  = "done"
    doc.parsed_at     = datetime.utcnow()
    db.commit()

    # Load CV with all relations for diff
    cv_full = (
        db.query(CV)
        .options(
            selectinload(CV.skills),
            selectinload(CV.references),
            selectinload(CV.educations),
            selectinload(CV.certifications),
            selectinload(CV.languages),
        )
        .filter(CV.id == cv.id)
        .first()
    )

    diff = compute_diff(cv_full, ai_result["data"])
    diff["document_id"] = doc.id
    return diff


# ── Endpoint: Apply diff ──────────────────────────────────────────────────────

@router.post("/apply")
def apply_diff(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Applica le modifiche selezionate dall'utente dopo la revisione del diff.

    Payload atteso:
    {
      document_id: int,
      profile_updates: { field: value, ... },
      skills:         { add: [...], update: [...] },
      references:     { add: [...], update: [...] },
      educations:     { add: [...], update: [...] },
      certifications: { add: [...], update: [...] },
      languages:      { add: [...], update: [...] }
    }
    """
    cv = (
        db.query(CV)
        .options(selectinload(CV.skills), selectinload(CV.references),
                 selectinload(CV.educations), selectinload(CV.certifications),
                 selectinload(CV.languages))
        .filter(CV.user_id == current_user.id)
        .first()
    )
    if not cv:
        raise HTTPException(404, "CV non trovato")

    applied: dict[str, int] = {
        "profile": 0, "skills": 0, "references": 0,
        "educations": 0, "certifications": 0, "languages": 0,
    }

    # ── Profilo ──
    for field, value in (payload.get("profile_updates") or {}).items():
        if hasattr(cv, field):
            setattr(cv, field, value or None)
            applied["profile"] += 1

    # ── Competenze ──
    sk_p = payload.get("skills") or {}
    existing_skill_names = {s.skill_name.lower() for s in cv.skills}
    for d in sk_p.get("add", []):
        if d["skill_name"].lower() in existing_skill_names:
            continue  # già presente, skip per idempotenza
        try:
            cat = SkillCategory(d.get("category", "HARD"))
        except ValueError:
            cat = SkillCategory.HARD
        db.add(CVSkill(cv_id=cv.id, skill_name=d["skill_name"],
                       category=cat, rating=d.get("rating"), notes=d.get("notes")))
        existing_skill_names.add(d["skill_name"].lower())
        applied["skills"] += 1
    for d in sk_p.get("update", []):
        sk = db.get(CVSkill, d.get("db_id"))
        if sk and sk.cv_id == cv.id:
            if "rating" in d:
                sk.rating = d["rating"]
            if "category" in d:
                try:
                    sk.category = SkillCategory(d["category"])
                except ValueError:
                    pass
            applied["skills"] += 1

    # -- Esperienze / Referenze --
    ref_p = payload.get("references") or {}
    def _ref_key(company: Optional[str], role: Optional[str], sd=None) -> str:
        """Chiave idempotenza referenze: azienda|ruolo|anno-inizio.
        Permette più esperienze nella stessa azienda con ruoli uguali ma anni diversi."""
        yr = str(_parse_date(sd).year) if _parse_date(sd) else ""
        return (company or "").lower().strip() + "|" + (role or "").lower().strip() + "|" + yr

    existing_refs = {_ref_key(r.company_name, r.role, str(r.start_date) if r.start_date else None) for r in cv.references}
    for d in ref_p.get("add", []):
        key = _ref_key(d.get("company_name"), d.get("role"), d.get("start_date"))
        if key in existing_refs:
            continue  # skip duplicati (idempotente)
        existing_refs.add(key)
        db.add(Reference(
            cv_id=cv.id,
            company_name=d.get("company_name"),
            client_name=d.get("client_name"),
            role=d.get("role"),
            start_date=_parse_date(d.get("start_date")),
            end_date=_parse_date(d.get("end_date")),
            is_current=bool(d.get("is_current", False)),
            project_description=d.get("project_description"),
            activities=d.get("activities"),
            skills_acquired=d.get("skills_acquired") or [],
        ))
        applied["references"] += 1
    for d in ref_p.get("update", []):
        ref = db.get(Reference, d.get("db_id"))
        if ref and ref.cv_id == cv.id:
            for f in ("company_name", "role", "project_description", "activities", "is_current"):
                if f in d:
                    setattr(ref, f, d[f])
            if "start_date" in d:
                ref.start_date = _parse_date(d["start_date"])
            if "end_date" in d:
                ref.end_date = _parse_date(d["end_date"])
            if "skills_acquired" in d:
                ref.skills_acquired = d.get("skills_acquired") or []
            applied["references"] += 1

    # -- Formazione --
    edu_p = payload.get("educations") or {}
    existing_edus = {(e.institution or "").lower() for e in cv.educations}
    for d in edu_p.get("add", []):
        inst_key = (d.get("institution") or "").lower()
        if inst_key in existing_edus:
            continue  # skip duplicati
        existing_edus.add(inst_key)
        # Map degree_type_raw -> DegreeLevel enum
        raw = (d.get("degree_type_raw") or d.get("degree_level") or "").upper()
        dl_map = {"DIPLOMA": DegreeLevel.DIPLOMA, "TRIENNALE": DegreeLevel.TRIENNALE,
                  "MAGISTRALE": DegreeLevel.MAGISTRALE, "DOTTORATO": DegreeLevel.DOTTORATO,
                  "MASTER": DegreeLevel.MASTER, "CORSO": DegreeLevel.CORSO}
        deg = next((v for k, v in dl_map.items() if k in raw), None)
        db.add(Education(
            cv_id=cv.id,
            institution=d.get("institution", ""),
            field_of_study=d.get("field_of_study"),
            graduation_year=d.get("graduation_year"),
            grade=d.get("grade"),
            degree_level=deg,
        ))
        applied["educations"] += 1
    for d in edu_p.get("update", []):
        edu = db.get(Education, d.get("db_id"))
        if edu and edu.cv_id == cv.id:
            for f in ("institution", "field_of_study", "graduation_year", "grade"):
                if f in d:
                    setattr(edu, f, d[f])
            applied["educations"] += 1

    # -- Certificazioni --
    cert_p = payload.get("certifications") or {}
    existing_certs = {(c.name or "").lower() for c in cv.certifications}
    for d in cert_p.get("add", []):
        cert_key = (d.get("name") or "").lower()
        if cert_key in existing_certs:
            continue  # skip duplicati
        existing_certs.add(cert_key)
        db.add(Certification(
            cv_id=cv.id,
            name=d.get("name", ""),
            issuing_org=d.get("issuing_org"),
            year=d.get("year"),
            expiry_date=_parse_date(d.get("expiry_date")),
            doc_url=d.get("doc_url"),
            doc_attachment_type=(DocAttachmentType.URL if d.get("doc_url") else DocAttachmentType.NONE),
        ))
        applied["certifications"] += 1
    for d in cert_p.get("update", []):
        cert = db.get(Certification, d.get("db_id"))
        if cert and cert.cv_id == cv.id:
            for f in ("name", "issuing_org", "year"):
                if f in d:
                    setattr(cert, f, d[f])
            if "expiry_date" in d:
                cert.expiry_date = _parse_date(d["expiry_date"])
            applied["certifications"] += 1

    # ── Lingue ──
    lang_p = payload.get("languages") or {}
    existing_langs = {l.language_name.lower() for l in cv.languages}
    for d in lang_p.get("add", []):
        if d.get("language_name", "").lower() in existing_langs:
            continue  # skip duplicates per idempotenza
        try:
            level = LanguageLevel(d.get("level")) if d.get("level") else None
        except ValueError:
            level = None
        db.add(Language(cv_id=cv.id, language_name=d.get("language_name", ""), level=level))
        existing_langs.add(d["language_name"].lower())
        applied["languages"] += 1
    for d in lang_p.get("update", []):
        lang = db.get(Language, d.get("db_id"))
        if lang and lang.cv_id == cv.id and "level" in d:
            try:
                lang.level = LanguageLevel(d["level"]) if d["level"] else None
            except ValueError:
                pass
            applied["languages"] += 1

    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(409, f"Conflitto dati: {str(e.orig)[:120]}") from e

    total = sum(applied.values())
    return {"success": True, "applied_count": total, "sections": applied,
            "message": f"{total} modifiche applicate con successo"}
