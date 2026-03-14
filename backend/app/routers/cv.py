"""
Router /cv — Sprint 2+.
GET/PUT /cv/me + CRUD sub-risorse + suggest endpoints + completeness dinamico.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
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
