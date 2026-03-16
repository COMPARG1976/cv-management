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


# ── Certificazioni — Upload documento (simulazione SharePoint) ────────────────

@router.post("/me/certifications/{cert_id}/upload-doc", response_model=CertificationResponse)
async def upload_cert_doc(
    cert_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Carica un documento allegato a una certificazione.
    Simula upload SharePoint salvando in uploads/certs/{user_id}/.
    Idempotente: sovrascrive il file precedente se stesso cert_id.
    """
    from app.models import DocAttachmentType

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

    original_name = file.filename or "document"
    ext = os.path.splitext(original_name)[1].lower() or ".bin"
    safe_name = f"cert_{cert_id}{ext}"

    cert_dir = os.path.join(settings.upload_dir, "certs", str(current_user.id))
    os.makedirs(cert_dir, exist_ok=True)

    file_path = os.path.join(cert_dir, safe_name)
    with open(file_path, "wb") as fh:
        fh.write(content_bytes)

    simulated_url = f"/uploads/certs/{current_user.id}/{safe_name}"

    cert.doc_url = simulated_url
    cert.doc_attachment_type = DocAttachmentType.SHAREPOINT
    db.commit()
    db.refresh(cert)
    return cert


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
            "status":          "existing" if badge_id in existing_ids else "new",
        })

    return {"username": username, "total": len(result), "badges": result}


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

        if badge_id in existing_map:
            cert = existing_map[badge_id]
            cert.name            = b.get("name", cert.name)
            cert.issuing_org     = b.get("issuing_org") or cert.issuing_org
            cert.year            = b.get("year") or cert.year
            cert.expiry_date     = b.get("expiry_date") or cert.expiry_date
            cert.badge_image_url = b.get("badge_image_url") or cert.badge_image_url
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
                doc_attachment_type=DocAttachmentType.CREDLY,
                has_formal_cert=True,
            )
            db.add(cert)
            imported += 1

    db.commit()
    return {"imported": imported, "updated": updated, "total": imported + updated}
