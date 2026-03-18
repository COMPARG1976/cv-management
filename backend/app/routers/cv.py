"""
Router /cv — Sprint 2+.
GET/PUT /cv/me + CRUD sub-risorse + suggest endpoints + completeness dinamico.
"""
import os
import re
from typing import List, Any, Dict

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.database import get_db, settings
from app.deps import get_current_user
from app.models import (
    User, CV, CVSkill, Education, Language, CVRole, Reference,
    Certification, AvailabilityStatus,
)
from app.schemas import (
    CVFullResponse, CVUpdate,
    CVSkillCreate, CVSkillResponse,
    EducationCreate, EducationResponse,
    LanguageCreate, LanguageResponse,
    CVRoleCreate, CVRoleResponse,
    ReferenceCreate, ReferenceResponse,
    CertificationCreate, CertificationResponse,
    SkillSuggestion, CertSuggestion,
)

router = APIRouter()

# ── Campi user vs cv ──────────────────────────────────────────────────────────
_USER_FIELDS = {"hire_date_mashfrog", "mashfrog_office", "bu_mashfrog"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sort_refs_key(ref: Reference):
    """Chiave sort: end_date DESC NULLS FIRST (posizioni correnti/null → prima), poi start_date DESC."""
    end_val = 999999 if (ref.is_current or ref.end_date is None) else (ref.end_date.year * 100 + ref.end_date.month)
    start_val = (ref.start_date.year * 100 + ref.start_date.month) if ref.start_date else 0
    return (-end_val, -start_val)


def _load_cv(user_id: int, db: Session) -> CV:
    """Carica CV con tutte le relazioni (crea se non esiste)."""
    cv = (
        db.query(CV)
        .options(
            selectinload(CV.skills),
            selectinload(CV.educations),
            selectinload(CV.languages),
            selectinload(CV.roles),
            selectinload(CV.references),
            selectinload(CV.certifications),
            selectinload(CV.documents),
        )
        .filter(CV.user_id == user_id)
        .first()
    )
    if not cv:
        cv = CV(user_id=user_id, availability_status=AvailabilityStatus.DISPONIBILE)
        db.add(cv)
        db.commit()
        return _load_cv(user_id, db)
    if cv.references:
        cv.references.sort(key=_sort_refs_key)
    return cv


def _get_cv_id(user_id: int, db: Session) -> int:
    """Restituisce cv.id, creando CV se non esiste."""
    row = db.query(CV.id).filter(CV.user_id == user_id).first()
    if not row:
        new_cv = CV(user_id=user_id, availability_status=AvailabilityStatus.DISPONIBILE)
        db.add(new_cv)
        db.flush()
        return new_cv.id
    return row[0]


def _404(detail: str):
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _compute_completeness(cv: CV, user: User) -> float:
    """Calcola completeness score 0-1 (scala 10 punti)."""
    pts = 0.0
    if cv.title:                pts += 1.0
    if cv.summary:              pts += 1.0
    if cv.phone:                pts += 0.5
    if cv.birth_date:           pts += 0.5
    if cv.residence_city:       pts += 0.5
    if user.hire_date_mashfrog: pts += 0.5
    if user.mashfrog_office:    pts += 0.5
    if cv.skills:               pts += 1.5
    if cv.educations:           pts += 1.0
    if cv.certifications:       pts += 1.0
    if cv.languages:            pts += 0.5
    if cv.references:           pts += 1.5
    return round(min(pts / 10.0, 1.0), 2)


def _make_full_response(cv: CV, user: User) -> CVFullResponse:
    """Costruisce CVFullResponse da CV ORM + User ORM."""
    resp = CVFullResponse.model_validate(cv)
    resp.completeness_score   = _compute_completeness(cv, user)
    resp.hire_date_mashfrog   = user.hire_date_mashfrog
    resp.mashfrog_office      = user.mashfrog_office
    resp.bu_mashfrog          = user.bu_mashfrog
    resp.full_name            = user.full_name
    return resp


# ── Autocomplete / Suggest ────────────────────────────────────────────────────

@router.get("/skills/suggest", response_model=List[SkillSuggestion])
def suggest_skills(
    q: str = Query(default=""),
    limit: int = Query(default=20, le=50),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Autocomplete skill_name con conteggio occorrenze (tutti i CV)."""
    query = (
        db.query(CVSkill.skill_name, CVSkill.category, func.count().label("cnt"))
        .group_by(CVSkill.skill_name, CVSkill.category)
    )
    if q:
        query = query.filter(CVSkill.skill_name.ilike(f"%{q}%"))
    rows = query.order_by(func.count().desc()).limit(limit).all()
    return [
        SkillSuggestion(skill_name=r.skill_name, category=r.category, count=r.cnt)
        for r in rows
    ]


@router.get("/certifications/suggest", response_model=List[CertSuggestion])
def suggest_certifications(
    q: str = Query(default=""),
    limit: int = Query(default=20, le=50),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Autocomplete cert_code con nome/org/versione aggregate."""
    query = (
        db.query(
            Certification.cert_code,
            Certification.name,
            Certification.issuing_org,
            Certification.version,
            func.count().label("cnt"),
        )
        .filter(
            Certification.cert_code.isnot(None),
            Certification.cert_code != "",
        )
        .group_by(
            Certification.cert_code,
            Certification.name,
            Certification.issuing_org,
            Certification.version,
        )
    )
    if q:
        query = query.filter(
            (Certification.cert_code.ilike(f"%{q}%"))
            | (Certification.name.ilike(f"%{q}%"))
        )
    rows = query.order_by(func.count().desc()).limit(limit).all()
    return [
        CertSuggestion(
            cert_code=r.cert_code,
            name=r.name,
            issuing_org=r.issuing_org,
            version=r.version,
            count=r.cnt,
        )
        for r in rows
    ]


# ── CV Hints (DB-driven, no AI) ───────────────────────────────────────────────

@router.get("/me/hints")
def get_my_cv_hints(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Suggerimenti contestuali basati sui dati del DB (no AI).
    - cert_hints: per ogni cert senza codice, suggerisce il codice più comune da CV simili
    - skill_hints: skill presenti in skills_acquired delle esperienze ma non nel profilo
    - experience_hints: esperienze senza descrizione o con descrizione molto breve
    - profile_hints: campi profilo mancanti importanti
    """
    cv = _load_cv(current_user.id, db)

    hints: dict[str, Any] = {
        "cert_hints": {},
        "skill_hints": [],
        "experience_hints": {},
        "profile_hints": [],
    }

    # 1. Cert hints: per ogni cert, suggerisce i campi mancanti da certs simili nel DB
    for cert in (cv.certifications or []):
        name_prefix = cert.name[:25] if len(cert.name) > 25 else cert.name
        # Trova le certs più simili negli altri CV
        similar = (
            db.query(Certification)
            .filter(
                Certification.cv_id != cv.id,
                Certification.name.ilike(f"%{name_prefix}%"),
            )
            .all()
        )
        if not similar:
            continue
        cert_hint: dict[str, Any] = {}

        # cert_code
        if not cert.cert_code:
            codes = [(c.cert_code, c) for c in similar if c.cert_code]
            if codes:
                # codice più frequente
                from collections import Counter
                most_common = Counter(c for c, _ in codes).most_common(1)[0]
                best = next(c for code, c in codes if code == most_common[0])
                cert_hint["cert_code"] = {"value": best.cert_code, "count": most_common[1]}

        # issuing_org
        if not cert.issuing_org:
            orgs = [c.issuing_org for c in similar if c.issuing_org]
            if orgs:
                cert_hint["issuing_org"] = {"value": Counter(orgs).most_common(1)[0][0]}

        # doc_url / verifica
        if not cert.doc_url:
            urls = [(c.doc_url, c.doc_attachment_type) for c in similar if c.doc_url]
            if urls:
                cert_hint["doc_url"] = {"value": urls[0][0], "attachment_type": urls[0][1].value if urls[0][1] else None}

        # expiry_date
        if not cert.expiry_date:
            expiries = [c.expiry_date for c in similar if c.expiry_date]
            if expiries:
                cert_hint["expiry_date"] = {"note": "Altri CV hanno una data di scadenza per questa certificazione"}

        if cert_hint:
            hints["cert_hints"][str(cert.id)] = cert_hint

    # 2. Skill hints: skill presenti in skills_acquired ma non nel profilo competenze
    existing = {s.skill_name.lower() for s in (cv.skills or [])}
    found: list[str] = []
    for ref in (cv.references or []):
        for sk in (ref.skills_acquired or []):
            if sk and sk.lower() not in existing and sk not in found:
                found.append(sk)
    hints["skill_hints"] = found[:12]

    # 3. Experience field hints: segnala campo per campo cosa manca
    for ref in (cv.references or []):
        exp_hint: dict[str, Any] = {}
        desc = (ref.project_description or "").strip()
        acts = (ref.activities or "").strip()
        if not desc and not acts:
            exp_hint["project_description"] = {"note": "Descrizione progetto assente"}
        elif len(desc) < 80 and len(acts) < 80:
            exp_hint["project_description"] = {"note": "Descrizione molto breve (< 80 caratteri)"}
        if not ref.role:
            exp_hint["role"] = {"note": "Ruolo non specificato"}
        if not ref.client_name:
            exp_hint["client_name"] = {"note": "Cliente finale non specificato"}
        if not ref.skills_acquired or len(ref.skills_acquired) == 0:
            exp_hint["skills_acquired"] = {"note": "Nessuna competenza acquisita indicata"}
        if not ref.start_date:
            exp_hint["start_date"] = {"note": "Data inizio assente"}
        if exp_hint:
            hints["experience_hints"][str(ref.id)] = exp_hint

    # 4. Profile hints: campi importanti mancanti
    if not cv.title:
        hints["profile_hints"].append({"field": "title", "label": "Titolo professionale mancante"})
    if not cv.summary or len(cv.summary.strip()) < 80:
        hints["profile_hints"].append({"field": "summary", "label": "Summary assente o troppo breve"})
    if not cv.phone:
        hints["profile_hints"].append({"field": "phone", "label": "Telefono mancante"})
    if not cv.linkedin_url:
        hints["profile_hints"].append({"field": "linkedin_url", "label": "LinkedIn mancante"})
    if not cv.residence_city:
        hints["profile_hints"].append({"field": "residence_city", "label": "Città di residenza mancante"})

    return hints


# ── GET / PUT /cv/me ──────────────────────────────────────────────────────────

@router.get("/me", response_model=CVFullResponse)
def get_my_cv(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cv = _load_cv(current_user.id, db)
    return _make_full_response(cv, current_user)


@router.put("/me", response_model=CVFullResponse)
def update_my_cv(
    data: CVUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cv_id = _get_cv_id(current_user.id, db)
    cv = db.query(CV).filter(CV.id == cv_id).first()

    for field, value in data.model_dump(exclude_none=True).items():
        if field in _USER_FIELDS:
            setattr(current_user, field, value)
        else:
            setattr(cv, field, value)

    db.commit()
    db.refresh(current_user)
    cv = _load_cv(current_user.id, db)
    return _make_full_response(cv, current_user)


# ── Skills ────────────────────────────────────────────────────────────────────

@router.post("/me/skills", response_model=CVSkillResponse, status_code=status.HTTP_201_CREATED)
def add_skill(
    data: CVSkillCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cv_id = _get_cv_id(current_user.id, db)
    skill = CVSkill(cv_id=cv_id, **data.model_dump())
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return skill


@router.put("/me/skills/{skill_id}", response_model=CVSkillResponse)
def update_skill(
    skill_id: int,
    data: CVSkillCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    skill = (
        db.query(CVSkill)
        .join(CV, CVSkill.cv_id == CV.id)
        .filter(CVSkill.id == skill_id, CV.user_id == current_user.id)
        .first()
    )
    if not skill:
        _404("Skill non trovata")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(skill, field, value)
    db.commit()
    db.refresh(skill)
    return skill


@router.delete("/me/skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_skill(
    skill_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    skill = (
        db.query(CVSkill)
        .join(CV, CVSkill.cv_id == CV.id)
        .filter(CVSkill.id == skill_id, CV.user_id == current_user.id)
        .first()
    )
    if not skill:
        _404("Skill non trovata")
    db.delete(skill)
    db.commit()


# ── Educations ────────────────────────────────────────────────────────────────

@router.post("/me/educations", response_model=EducationResponse, status_code=status.HTTP_201_CREATED)
def add_education(
    data: EducationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cv_id = _get_cv_id(current_user.id, db)
    edu = Education(cv_id=cv_id, **data.model_dump())
    db.add(edu)
    db.commit()
    db.refresh(edu)
    return edu


@router.put("/me/educations/{edu_id}", response_model=EducationResponse)
def update_education(
    edu_id: int,
    data: EducationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    edu = (
        db.query(Education)
        .join(CV, Education.cv_id == CV.id)
        .filter(Education.id == edu_id, CV.user_id == current_user.id)
        .first()
    )
    if not edu:
        _404("Titolo di studio non trovato")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(edu, field, value)
    db.commit()
    db.refresh(edu)
    return edu


@router.delete("/me/educations/{edu_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_education(
    edu_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    edu = (
        db.query(Education)
        .join(CV, Education.cv_id == CV.id)
        .filter(Education.id == edu_id, CV.user_id == current_user.id)
        .first()
    )
    if not edu:
        _404("Titolo di studio non trovato")
    db.delete(edu)
    db.commit()


# ── Languages ─────────────────────────────────────────────────────────────────

@router.post("/me/languages", response_model=LanguageResponse, status_code=status.HTTP_201_CREATED)
def add_language(
    data: LanguageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cv_id = _get_cv_id(current_user.id, db)
    lang = Language(cv_id=cv_id, **data.model_dump())
    db.add(lang)
    db.commit()
    db.refresh(lang)
    return lang


@router.put("/me/languages/{lang_id}", response_model=LanguageResponse)
def update_language(
    lang_id: int,
    data: LanguageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lang = (
        db.query(Language)
        .join(CV, Language.cv_id == CV.id)
        .filter(Language.id == lang_id, CV.user_id == current_user.id)
        .first()
    )
    if not lang:
        _404("Lingua non trovata")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(lang, field, value)
    db.commit()
    db.refresh(lang)
    return lang


@router.delete("/me/languages/{lang_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_language(
    lang_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    lang = (
        db.query(Language)
        .join(CV, Language.cv_id == CV.id)
        .filter(Language.id == lang_id, CV.user_id == current_user.id)
        .first()
    )
    if not lang:
        _404("Lingua non trovata")
    db.delete(lang)
    db.commit()


# ── Roles ─────────────────────────────────────────────────────────────────────

@router.post("/me/roles", response_model=CVRoleResponse, status_code=status.HTTP_201_CREATED)
def add_role(
    data: CVRoleCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cv_id = _get_cv_id(current_user.id, db)
    role = CVRole(cv_id=cv_id, **data.model_dump())
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


@router.delete("/me/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(
    role_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    role = (
        db.query(CVRole)
        .join(CV, CVRole.cv_id == CV.id)
        .filter(CVRole.id == role_id, CV.user_id == current_user.id)
        .first()
    )
    if not role:
        _404("Ruolo non trovato")
    db.delete(role)
    db.commit()


# ── References ────────────────────────────────────────────────────────────────

@router.post("/me/references", response_model=ReferenceResponse, status_code=status.HTTP_201_CREATED)
def add_reference(
    data: ReferenceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cv_id = _get_cv_id(current_user.id, db)
    ref = Reference(cv_id=cv_id, **data.model_dump())
    db.add(ref)
    db.commit()
    db.refresh(ref)
    return ref


@router.put("/me/references/{ref_id}", response_model=ReferenceResponse)
def update_reference(
    ref_id: int,
    data: ReferenceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ref = (
        db.query(Reference)
        .join(CV, Reference.cv_id == CV.id)
        .filter(Reference.id == ref_id, CV.user_id == current_user.id)
        .first()
    )
    if not ref:
        _404("Esperienza non trovata")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(ref, field, value)
    db.commit()
    db.refresh(ref)
    return ref


@router.delete("/me/references/{ref_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reference(
    ref_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ref = (
        db.query(Reference)
        .join(CV, Reference.cv_id == CV.id)
        .filter(Reference.id == ref_id, CV.user_id == current_user.id)
        .first()
    )
    if not ref:
        _404("Esperienza non trovata")
    db.delete(ref)
    db.commit()


# ── Certifications ────────────────────────────────────────────────────────────

@router.post("/me/certifications", response_model=CertificationResponse, status_code=status.HTTP_201_CREATED)
def add_certification(
    data: CertificationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cv_id = _get_cv_id(current_user.id, db)
    cert = Certification(cv_id=cv_id, **data.model_dump())
    db.add(cert)
    db.commit()
    db.refresh(cert)
    return cert


@router.put("/me/certifications/{cert_id}", response_model=CertificationResponse)
def update_certification(
    cert_id: int,
    data: CertificationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cert = (
        db.query(Certification)
        .join(CV, Certification.cv_id == CV.id)
        .filter(Certification.id == cert_id, CV.user_id == current_user.id)
        .first()
    )
    if not cert:
        _404("Certificazione non trovata")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(cert, field, value)
    db.commit()
    db.refresh(cert)
    return cert


@router.delete("/me/certifications/{cert_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_certification(
    cert_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cert = (
        db.query(Certification)
        .join(CV, Certification.cv_id == CV.id)
        .filter(Certification.id == cert_id, CV.user_id == current_user.id)
        .first()
    )
    if not cert:
        _404("Certificazione non trovata")
    db.delete(cert)
    db.commit()


# ── Certificazioni — Upload documento (sempre disponibile, tutti i tipi) ───────

@router.post("/me/certifications/{cert_id}/upload-doc", response_model=CertificationResponse)
async def upload_cert_doc(
    cert_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Carica un file allegato a una certificazione (PDF, immagine, docx — max 10 MB).
    Se SharePoint e' configurato salva su SP (STAFF_DATA_AND_DOCUMENTS/{email}/Certificazioni/).
    Altrimenti salva in locale (uploads/certs/{user_id}/).
    Idempotente: sovrascrive il file precedente.
    """
    cert = (
        db.query(Certification)
        .join(CV, Certification.cv_id == CV.id)
        .filter(Certification.id == cert_id, CV.user_id == current_user.id)
        .first()
    )
    if not cert:
        _404("Certificazione non trovata")

    content_bytes = await file.read()
    if len(content_bytes) > 10 * 1024 * 1024:
        raise HTTPException(400, "File troppo grande (max 10 MB)")

    ext = os.path.splitext(file.filename or "doc")[1].lower() or ".bin"
    allowed = {".pdf", ".jpg", ".jpeg", ".png", ".docx", ".doc"}
    if ext not in allowed:
        raise HTTPException(400, f"Formato non supportato ({ext}). Ammessi: pdf, jpg, png, docx")

    if settings.sharepoint_enabled:
        # ── SharePoint ──────────────────────────────────────────────────────
        from app.sharepoint import upload_cert_file
        try:
            sp_path = await upload_cert_file(
                user_email=current_user.email,
                cert_id=cert_id,
                original_filename=file.filename or f"cert_{cert_id}{ext}",
                content=content_bytes,
                user_full_name=current_user.full_name or "",
                cert_name=cert.name or "",
            )
            cert.uploaded_file_path = f"sp:{sp_path}"
        except Exception as e:
            raise HTTPException(502, f"Errore upload SharePoint: {e}")
    else:
        # ── Storage locale (fallback) ───────────────────────────────────────
        safe_name = f"cert_{cert_id}{ext}"
        cert_dir  = os.path.join(settings.upload_dir, "certs", str(current_user.id))
        os.makedirs(cert_dir, exist_ok=True)
        with open(os.path.join(cert_dir, safe_name), "wb") as fh:
            fh.write(content_bytes)
        cert.uploaded_file_path = f"/uploads/certs/{current_user.id}/{safe_name}"

    db.commit()
    db.refresh(cert)
    return cert


@router.delete("/me/certifications/{cert_id}/upload-doc", status_code=204)
async def delete_cert_doc(
    cert_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Rimuove il file allegato (da SharePoint o da disco locale)."""
    cert = (
        db.query(Certification)
        .join(CV, Certification.cv_id == CV.id)
        .filter(Certification.id == cert_id, CV.user_id == current_user.id)
        .first()
    )
    if not cert:
        _404("Certificazione non trovata")

    if cert.uploaded_file_path:
        if cert.uploaded_file_path.startswith("sp:"):
            # ── SharePoint ─────────────────────────────────────────────────
            from app.sharepoint import delete_file
            try:
                await delete_file(cert.uploaded_file_path[3:])
            except Exception:
                pass  # Non bloccare la UI se il file non esiste più su SP
        else:
            # ── Storage locale ──────────────────────────────────────────────
            rel      = cert.uploaded_file_path.lstrip("/uploads/").lstrip("uploads/")
            abs_path = os.path.join(settings.upload_dir, rel)
            if os.path.exists(abs_path):
                os.remove(abs_path)

        cert.uploaded_file_path = None
        db.commit()


@router.get("/me/certifications/{cert_id}/download-doc")
async def download_cert_doc(
    cert_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Scarica il file allegato.
    - SharePoint: redirect a URL pre-firmato Graph API (~1h di validita')
    - Locale: FileResponse diretto
    """
    from fastapi.responses import FileResponse, RedirectResponse

    cert = (
        db.query(Certification)
        .join(CV, Certification.cv_id == CV.id)
        .filter(Certification.id == cert_id, CV.user_id == current_user.id)
        .first()
    )
    if not cert:
        _404("Certificazione non trovata")
    if not cert.uploaded_file_path:
        raise HTTPException(404, "Nessun file allegato per questa certificazione")

    if cert.uploaded_file_path.startswith("sp:"):
        # ── SharePoint ──────────────────────────────────────────────────────
        from app.sharepoint import get_download_url
        try:
            url = await get_download_url(cert.uploaded_file_path[3:])
        except Exception as e:
            raise HTTPException(502, f"Impossibile ottenere URL da SharePoint: {e}")
        return RedirectResponse(url)
    else:
        # ── Storage locale ──────────────────────────────────────────────────
        rel      = cert.uploaded_file_path.lstrip("/")
        abs_path = os.path.join("/app", rel)
        if not os.path.exists(abs_path):
            raise HTTPException(404, "File non trovato su disco")
        filename = os.path.basename(abs_path)
        return FileResponse(abs_path, filename=filename, media_type="application/octet-stream")


# ── Certificazioni — Credly preview ───────────────────────────────────────────

@router.get("/certifications/credly/preview")
async def credly_preview(
    url: str = Query(..., description="URL profilo Credly"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict:
    """
    Legge i badge dal profilo Credly pubblico e li confronta con le cert nel DB.
    Restituisce lista badge con status: new | existing.
    """
    match = re.search(r'credly\.com/users/([^/#?]+)', url)
    if not match:
        raise HTTPException(400, "URL Credly non valido. Formato: https://www.credly.com/users/<username>")
    username = match.group(1)
    badges_url = f"https://www.credly.com/users/{username}/badges.json"

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(badges_url, headers={"Accept": "application/json"})
    if resp.status_code != 200:
        raise HTTPException(502, f"Impossibile accedere al profilo Credly (HTTP {resp.status_code})")

    raw = resp.json()
    if isinstance(raw, list):
        badges_raw = raw
    elif isinstance(raw, dict):
        badges_raw = raw.get("data", raw.get("badges", []))
    else:
        badges_raw = []

    cv = db.query(CV).filter(CV.user_id == current_user.id).first()
    existing_ids: set = set()
    if cv:
        existing_ids = {c.credly_badge_id for c in cv.certifications if c.credly_badge_id}

    result = []
    for b in badges_raw:
        badge_id = b.get("id", "")
        tpl = b.get("badge_template", {}) or {}
        name = tpl.get("name", "")
        if not name:
            continue

        issuer_entities = (b.get("issuer") or {}).get("entities", [])
        issuing_org = ""
        if issuer_entities:
            issuing_org = issuer_entities[0].get("entity", {}).get("name", "")

        issued_at = b.get("issued_at_date", "") or ""
        year = int(issued_at[:4]) if len(issued_at) >= 4 else None
        expires_at = b.get("expires_at_date")
        expiry_date = expires_at[:10] if expires_at else None

        image_url = tpl.get("image_url", "") or (tpl.get("image") or {}).get("url", "")

        skills = tpl.get("skills", []) or []
        skills_csv = ", ".join(s.get("name", "") for s in skills if s.get("name"))

        result.append({
            "credly_badge_id": badge_id,
            "name":            name,
            "issuing_org":     issuing_org,
            "year":            year,
            "expiry_date":     expiry_date,
            "badge_image_url": image_url,
            "skills_csv":      skills_csv,
            "cert_code":       None,
            "status":          "existing" if badge_id in existing_ids else "new",
        })

    return {"username": username, "total": len(result), "badges": result}


# ── Certificazioni — Credly PDF download ──────────────────────────────────────

@router.get("/me/certifications/{cert_id}/credly-pdf")
async def download_credly_pdf(
    cert_id: int,
    save: bool = Query(False, description="Se true, salva il PDF come allegato"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Scarica il PDF stampabile di un badge Credly.
    Richiede che la certificazione abbia credly_badge_id valorizzato.
    Recupera l'URL firmato dalla API pubblica Credly e redirige al download.
    Se save=true, salva il PDF come uploaded_file_path della certificazione.
    """
    from fastapi.responses import RedirectResponse, StreamingResponse

    cert = (
        db.query(Certification)
        .join(CV, Certification.cv_id == CV.id)
        .filter(Certification.id == cert_id, CV.user_id == current_user.id)
        .first()
    )
    if not cert:
        _404("Certificazione non trovata")
    if not cert.credly_badge_id:
        raise HTTPException(400, "Questa certificazione non ha un badge Credly collegato")

    badge_id = cert.credly_badge_id

    # Prova API pubblica Credly per ottenere l'URL del PDF stampabile
    pdf_url: Optional[str] = None

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        # Endpoint JSON pubblico del badge
        resp = await client.get(
            f"https://www.credly.com/badges/{badge_id}.json",
            headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
        )
        if resp.status_code == 200:
            try:
                data = resp.json()
                # Cerca URL PDF nei campi noti della risposta Credly
                for key in ("pdf_download_url", "printable_pdf", "pdf_url"):
                    if data.get(key):
                        pdf_url = data[key]
                        break
                # Alcuni campi sono annidati
                if not pdf_url and isinstance(data.get("data"), dict):
                    inner = data["data"]
                    for key in ("pdf_download_url", "printable_pdf", "pdf_url"):
                        if inner.get(key):
                            pdf_url = inner[key]
                            break
            except Exception:
                pass

        # Fallback: endpoint API ufficiale Credly
        if not pdf_url:
            resp2 = await client.get(
                f"https://api.credly.com/v1/badges/{badge_id}",
                headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
            )
            if resp2.status_code == 200:
                try:
                    data2 = resp2.json()
                    badge_data = data2.get("data", data2)
                    for key in ("pdf_download_url", "printable_pdf", "pdf_url"):
                        if badge_data.get(key):
                            pdf_url = badge_data[key]
                            break
                except Exception:
                    pass

        if not pdf_url:
            raise HTTPException(
                502,
                "Impossibile ottenere il PDF da Credly. "
                "Il badge potrebbe non avere un PDF stampabile disponibile."
            )

        if save:
            # Scarica e salva come uploaded_file_path
            pdf_resp = await client.get(pdf_url, headers={"User-Agent": "Mozilla/5.0"})
            if pdf_resp.status_code != 200:
                raise HTTPException(502, "Download PDF da Credly fallito")

            cert_dir = os.path.join(settings.upload_dir, "certs", str(current_user.id))
            os.makedirs(cert_dir, exist_ok=True)
            file_name = f"cert_{cert_id}_credly.pdf"
            file_path = os.path.join(cert_dir, file_name)
            with open(file_path, "wb") as fh:
                fh.write(pdf_resp.content)

            cert.uploaded_file_path = f"/uploads/certs/{current_user.id}/{file_name}"
            db.commit()
            db.refresh(cert)

            # Restituisce il file direttamente
            import io
            return StreamingResponse(
                io.BytesIO(pdf_resp.content),
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
            )

    # Redirect diretto all'URL firmato Credly (download immediato senza salvare)
    return RedirectResponse(url=pdf_url, status_code=302)


# ── Certificazioni — Credly import ────────────────────────────────────────────

@router.post("/certifications/credly/import")
def credly_import(
    payload: Dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict:
    """
    Importa/aggiorna certificazioni da Credly.
    payload = {"badges": [...]}
    Idempotente: se credly_badge_id esiste aggiorna, altrimenti crea.
    """
    from app.models import DocAttachmentType

    badges = payload.get("badges", [])
    if not badges:
        raise HTTPException(400, "Nessun badge da importare")

    cv_id = _get_cv_id(current_user.id, db)

    existing_certs = (
        db.query(Certification)
        .filter(
            Certification.cv_id == cv_id,
            Certification.credly_badge_id.isnot(None),
        )
        .all()
    )
    existing_map: Dict[str, Certification] = {c.credly_badge_id: c for c in existing_certs}

    imported = 0
    updated = 0
    for b in badges:
        badge_id = b.get("credly_badge_id", "")
        if not badge_id or not b.get("name"):
            continue

        badge_url = f"https://www.credly.com/badges/{badge_id}"
        if badge_id in existing_map:
            cert = existing_map[badge_id]
            cert.name            = b.get("name", cert.name)
            cert.issuing_org     = b.get("issuing_org") or cert.issuing_org
            cert.year            = b.get("year") or cert.year
            cert.expiry_date     = b.get("expiry_date") or cert.expiry_date
            cert.badge_image_url = b.get("badge_image_url") or cert.badge_image_url
            cert.doc_url         = badge_url
            cert.doc_attachment_type = DocAttachmentType.CREDLY
            updated += 1
        else:
            cert = Certification(
                cv_id=cv_id,
                name=b["name"],
                issuing_org=b.get("issuing_org") or None,
                year=b.get("year"),
                expiry_date=b.get("expiry_date") or None,
                credly_badge_id=badge_id,
                badge_image_url=b.get("badge_image_url") or None,
                doc_url=badge_url,
                doc_attachment_type=DocAttachmentType.CREDLY,
                has_formal_cert=True,
            )
            db.add(cert)
            imported += 1

    db.commit()
    return {"imported": imported, "updated": updated, "total": imported + updated}


# ── Cert Catalog — suggest codes ──────────────────────────────────────────────

@router.post("/cert-catalog/suggest-codes")
def cert_catalog_suggest_codes(
    payload: Dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Dato un dizionario {cert_id: name}, restituisce il miglior match
    tra le certificazioni già salvate nel DB che hanno cert_code valorizzato.
    Usato per suggerire codici su cert esistenti senza codice.

    Algoritmo: max(SequenceMatcher, Jaccard sui token).
    """
    from difflib import SequenceMatcher
    import unicodedata

    names: Dict[str, str] = payload.get("names", {})
    if not names:
        return {}

    # Fonte: certificazioni già inserite da qualsiasi utente con cert_code valorizzato.
    # Deduplicate per (name, cert_code) per non avere migliaia di copie identiche.
    existing = (
        db.query(Certification.name, Certification.cert_code)
        .filter(Certification.cert_code.isnot(None), Certification.cert_code != "")
        .distinct()
        .all()
    )
    if not existing:
        return {}

    # Stop words: solo parole non-discriminanti (preposizioni, brand, verbi generici)
    # NON includere ruoli (administrator, business, user, analyst, developer) — sono discriminanti!
    _STOP = {
        "certified", "opentext", "for", "the", "in", "of", "a", "an",
        "using", "managing", "configuring", "implementing",
        "technology", "sap",
    }

    def _tokens(s: str) -> set:
        words = re.sub(r"[^a-z0-9]", " ", s.lower()).split()
        return {w for w in words if w not in _STOP and len(w) > 2}

    def norm(s: str) -> str:
        s = unicodedata.normalize("NFD", s.lower())
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        s = re.sub(r'[^a-z0-9\s]', ' ', s)
        s = re.sub(r'\b(sap certified|certified|associate|professional|specialist|application|development|technology)\b', '', s)
        return re.sub(r'\s+', ' ', s).strip()

    # Pre-calcola normalizzazione e token per ogni entry disponibile
    cat_data = [(norm(row.name), _tokens(row.name), row) for row in existing]
    result = {}

    for cert_id, name in names.items():
        n = norm(name)
        ct = _tokens(name)
        best_score, best_row = 0.0, None
        for cat_n, cat_tokens, row in cat_data:
            seq = SequenceMatcher(None, n, cat_n).ratio()
            union = ct | cat_tokens
            jaccard = len(ct & cat_tokens) / len(union) if union else 0.0
            s = max(seq, jaccard)
            if s > best_score:
                best_score, best_row = s, row
        if best_row and best_score >= 0.80:
            result[cert_id] = {
                "name":      best_row.name,
                "cert_code": best_row.cert_code,
                "score":     round(best_score, 3),
            }

    return result
