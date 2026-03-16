"""
Pydantic v2 schemas per request/response.
"""
from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, EmailStr, ConfigDict

from app.models import (
    UserRole, SkillCategory, DegreeLevel, LanguageLevel,
    AvailabilityStatus, DocAttachmentType
)


# ── Auth ──────────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    full_name: str
    email: str


class AuthConfig(BaseModel):
    provider: str


# ── User ──────────────────────────────────────────────────────────────────────

class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: UserRole = UserRole.USER
    username: Optional[str] = None
    bu_mashfrog: Optional[str] = None
    mashfrog_office: Optional[str] = None
    hire_date_mashfrog: Optional[date] = None


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    bu_mashfrog: Optional[str] = None
    mashfrog_office: Optional[str] = None
    hire_date_mashfrog: Optional[date] = None


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_active: bool
    created_at: datetime


# ── Education ─────────────────────────────────────────────────────────────────

class EducationBase(BaseModel):
    institution: str
    degree_level: Optional[DegreeLevel] = None
    field_of_study: Optional[str] = None
    graduation_year: Optional[int] = None
    graduation_date: Optional[date] = None
    grade: Optional[str] = None
    notes: Optional[str] = None


class EducationCreate(EducationBase):
    pass


class EducationResponse(EducationBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ── Language ──────────────────────────────────────────────────────────────────

class LanguageBase(BaseModel):
    language_name: str
    level: Optional[LanguageLevel] = None


class LanguageCreate(LanguageBase):
    pass


class LanguageResponse(LanguageBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ── CVRole ────────────────────────────────────────────────────────────────────

class CVRoleBase(BaseModel):
    title: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_current: bool = False
    company: Optional[str] = None
    notes: Optional[str] = None


class CVRoleCreate(CVRoleBase):
    pass


class CVRoleResponse(CVRoleBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ── CVSkill ───────────────────────────────────────────────────────────────────

class CVSkillBase(BaseModel):
    skill_name: str
    category: SkillCategory
    rating: Optional[int] = None   # 1-5
    notes: Optional[str] = None


class CVSkillCreate(CVSkillBase):
    pass


class CVSkillResponse(CVSkillBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ── Reference ─────────────────────────────────────────────────────────────────

class ReferenceBase(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_current: bool = False
    company_name: Optional[str] = None
    client_name: Optional[str] = None
    role: Optional[str] = None
    project_description: Optional[str] = None
    activities: Optional[str] = None
    skills_acquired: Optional[List[str]] = None
    sort_order: int = 0


class ReferenceCreate(ReferenceBase):
    pass


class ReferenceResponse(ReferenceBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ── Certification ─────────────────────────────────────────────────────────────

class CertificationBase(BaseModel):
    year: Optional[int] = None
    issuing_org: Optional[str] = None
    cert_code: Optional[str] = None
    name: str
    version: Optional[str] = None
    expiry_date: Optional[date] = None
    notes: Optional[str] = None
    doc_attachment_type: DocAttachmentType = DocAttachmentType.NONE
    doc_url: Optional[str] = None
    has_formal_cert: bool = True
    credly_badge_id: Optional[str] = None
    badge_image_url: Optional[str] = None


class CertificationCreate(CertificationBase):
    pass


class CertificationResponse(CertificationBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ── CVDocument ────────────────────────────────────────────────────────────────

class CVDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    original_filename: str
    sharepoint_url: Optional[str]
    mime_type: str
    file_size_bytes: Optional[int]
    uploaded_at: datetime
    parse_status: str


# ── CV (completo) ─────────────────────────────────────────────────────────────

class CVUpdate(BaseModel):
    # CV fields
    birth_date: Optional[date] = None
    birth_place: Optional[str] = None
    residence_city: Optional[str] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    first_employment_date: Optional[date] = None
    availability_status: Optional[AvailabilityStatus] = None
    # User-level fields (stored on User model, updated via same endpoint)
    hire_date_mashfrog: Optional[date] = None
    mashfrog_office: Optional[str] = None
    bu_mashfrog: Optional[str] = None


class CVResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    birth_date: Optional[date]
    birth_place: Optional[str]
    residence_city: Optional[str]
    title: Optional[str]
    summary: Optional[str]
    phone: Optional[str]
    linkedin_url: Optional[str]
    first_employment_date: Optional[date]
    availability_status: AvailabilityStatus
    completeness_score: float
    educations: List[EducationResponse] = []
    languages: List[LanguageResponse] = []
    roles: List[CVRoleResponse] = []
    skills: List[CVSkillResponse] = []
    references: List[ReferenceResponse] = []
    certifications: List[CertificationResponse] = []
    documents: List[CVDocumentResponse] = []
    updated_at: datetime


# ── Search (API pubblica) ─────────────────────────────────────────────────────

class ResourceSummary(BaseModel):
    """Schema per API pubblica consumata da IT_RESOURCE_MGMT e altri servizi."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    full_name: str
    email: str
    username: Optional[str]
    bu_mashfrog: Optional[str]
    mashfrog_office: Optional[str]
    title: Optional[str]
    availability_status: Optional[AvailabilityStatus]
    skills: List[CVSkillResponse] = []


# ── Autocomplete (suggest) ────────────────────────────────────────────────────

class SkillSuggestion(BaseModel):
    skill_name: str
    category: SkillCategory
    count: int


class CertSuggestion(BaseModel):
    cert_code: str
    name: str
    issuing_org: Optional[str] = None
    version: Optional[str] = None
    count: int = 1


# ── Skill Taxonomy ────────────────────────────────────────────────────────────

class SkillTaxonomyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    category: Optional[SkillCategory]
    usage_count: int


# ── CVFullResponse (CV + campi User) ─────────────────────────────────────────

class CVFullResponse(CVResponse):
    """CVResponse arricchito con campi dell'utente (sede, data assunzione, BU)."""
    hire_date_mashfrog: Optional[date] = None
    mashfrog_office: Optional[str] = None
    bu_mashfrog: Optional[str] = None
    full_name: Optional[str] = None


# (SkillSuggestion e CertSuggestion definiti sopra — nessun duplicato)


