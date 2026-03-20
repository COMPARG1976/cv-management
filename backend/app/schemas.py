"""
Pydantic v2 schemas per request/response.
Nessuna dipendenza da ORM/SQLAlchemy — tutti i tipi sono stringhe o primitivi.
"""
from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, EmailStr


# ── Auth ──────────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    full_name: str
    email: str


class AuthConfig(BaseModel):
    provider: str
    entra_enabled: bool = False
    entra_client_id: Optional[str] = None
    entra_tenant_id: Optional[str] = None
    entra_redirect_uri: Optional[str] = None


class EntraExchangeRequest(BaseModel):
    code: str
    redirect_uri: str


# ── User ──────────────────────────────────────────────────────────────────────

class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: str = "USER"
    username: Optional[str] = None
    bu_mashfrog: Optional[str] = None
    mashfrog_office: Optional[str] = None
    hire_date_mashfrog: Optional[date] = None


class UserCreate(UserBase):
    pass


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    bu_mashfrog: Optional[str] = None
    mashfrog_office: Optional[str] = None
    hire_date_mashfrog: Optional[date] = None


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str = "USER"
    username: Optional[str] = None
    bu_mashfrog: Optional[str] = None
    mashfrog_office: Optional[str] = None
    hire_date: Optional[str] = None
    is_active: bool = True
    created_at: Optional[str] = None


# ── Education ─────────────────────────────────────────────────────────────────

class EducationBase(BaseModel):
    institution: str
    degree_level: Optional[str] = None
    field_of_study: Optional[str] = None
    graduation_year: Optional[int] = None
    graduation_date: Optional[date] = None
    grade: Optional[str] = None
    notes: Optional[str] = None


class EducationCreate(EducationBase):
    pass


class EducationResponse(EducationBase):
    id: str


# ── Language ──────────────────────────────────────────────────────────────────

class LanguageBase(BaseModel):
    language_name: str
    level: Optional[str] = None


class LanguageCreate(LanguageBase):
    pass


class LanguageResponse(LanguageBase):
    id: str


# ── CVSkill ───────────────────────────────────────────────────────────────────

class CVSkillBase(BaseModel):
    skill_name: str
    category: str = "HARD"
    rating: Optional[int] = None
    notes: Optional[str] = None


class CVSkillCreate(CVSkillBase):
    pass


class CVSkillResponse(CVSkillBase):
    id: str


# ── Reference (esperienze) ────────────────────────────────────────────────────

class ReferenceBase(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_current: bool = False
    company_name: Optional[str] = None
    client_name: Optional[str] = None
    role: Optional[str] = None
    project_description: Optional[str] = None
    activities: Optional[str] = None
    sort_order: int = 0


class ReferenceCreate(ReferenceBase):
    pass


class ReferenceResponse(ReferenceBase):
    id: str


# ── Certification ─────────────────────────────────────────────────────────────

class CertificationBase(BaseModel):
    year: Optional[int] = None
    issuing_org: Optional[str] = None
    cert_code: Optional[str] = None
    name: str
    version: Optional[str] = None
    expiry_date: Optional[date] = None
    notes: Optional[str] = None
    doc_attachment_type: str = "NONE"
    doc_url: Optional[str] = None
    has_formal_cert: bool = True
    credly_badge_id: Optional[str] = None
    badge_image_url: Optional[str] = None
    tags: Optional[List[str]] = None


class CertificationCreate(CertificationBase):
    pass


class CertificationResponse(CertificationBase):
    id: str
    uploaded_file_path: Optional[str] = None


# ── CVDocument ────────────────────────────────────────────────────────────────

class CVDocumentResponse(BaseModel):
    id: str
    original_filename: str
    doc_type: str = "UPLOAD"
    sharepoint_path: Optional[str] = None
    sharepoint_url: Optional[str] = None
    upload_date: Optional[str] = None
    ai_updated: bool = False
    tags: Optional[List[str]] = None


# ── CV Update ─────────────────────────────────────────────────────────────────

class CVUpdate(BaseModel):
    birth_date: Optional[date] = None
    birth_place: Optional[str] = None
    residence_city: Optional[str] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    first_employment_date: Optional[date] = None
    availability_status: Optional[str] = None
    hire_date_mashfrog: Optional[date] = None
    mashfrog_office: Optional[str] = None
    bu_mashfrog: Optional[str] = None


# ── CV Full Response ──────────────────────────────────────────────────────────

class CVFullResponse(BaseModel):
    """Profilo CV completo con tutti i sotto-oggetti e campi utente."""
    email: str
    # Profilo
    title: Optional[str] = None
    summary: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    birth_date: Optional[str] = None
    birth_place: Optional[str] = None
    residence_city: Optional[str] = None
    first_employment_date: Optional[str] = None
    availability_status: str = "IN_STAFF"
    completeness_score: float = 0.0
    updated_at: Optional[str] = None
    # Campi utente
    full_name: Optional[str] = None
    hire_date_mashfrog: Optional[str] = None
    mashfrog_office: Optional[str] = None
    bu_mashfrog: Optional[str] = None
    # Sotto-collezioni
    educations: List[EducationResponse] = []
    languages: List[LanguageResponse] = []
    skills: List[CVSkillResponse] = []
    references: List[ReferenceResponse] = []
    certifications: List[CertificationResponse] = []
    documents: List[CVDocumentResponse] = []


# ── Search ────────────────────────────────────────────────────────────────────

class ResourceSummary(BaseModel):
    id: str
    full_name: str
    email: str
    username: Optional[str] = None
    bu_mashfrog: Optional[str] = None
    mashfrog_office: Optional[str] = None
    title: Optional[str] = None
    availability_status: Optional[str] = None
    skills: List[CVSkillResponse] = []


# ── Autocomplete ──────────────────────────────────────────────────────────────

class SkillSuggestion(BaseModel):
    skill_name: str
    category: str
    count: int


class CertSuggestion(BaseModel):
    cert_code: str
    name: str
    issuing_org: Optional[str] = None
    version: Optional[str] = None
    count: int = 1
