"""
SQLAlchemy ORM models per CV Management System.
Schema: User (1:1) CV ─── Education, Language, CVRole, CVSkill, Reference, Certification, CVDocument
"""
import enum
from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import (
    Integer, SmallInteger, String, Text, Boolean, Float, DateTime, Date,
    ForeignKey, Enum, UniqueConstraint, Index, func, text
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from app.database import Base


# ── Enum Types ────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    USER = "USER"
    ADMIN = "ADMIN"


class SkillCategory(str, enum.Enum):
    HARD = "HARD"
    SOFT = "SOFT"


class DegreeLevel(str, enum.Enum):
    DIPLOMA = "DIPLOMA"
    TRIENNALE = "TRIENNALE"
    MAGISTRALE = "MAGISTRALE"
    DOTTORATO = "DOTTORATO"
    MASTER = "MASTER"
    CORSO = "CORSO"


class LanguageLevel(str, enum.Enum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"
    MADRELINGUA = "MADRELINGUA"


class AvailabilityStatus(str, enum.Enum):
    DISPONIBILE = "DISPONIBILE"
    OCCUPATO = "OCCUPATO"
    IN_USCITA = "IN_USCITA"


class DocAttachmentType(str, enum.Enum):
    SHAREPOINT = "SHAREPOINT"
    CREDLY = "CREDLY"
    URL = "URL"
    NONE = "NONE"


# ── User ──────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(100), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False, default=UserRole.USER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Dati aziendali
    bu_mashfrog: Mapped[Optional[str]] = mapped_column(String(100))       # BU di appartenenza
    mashfrog_office: Mapped[Optional[str]] = mapped_column(String(100))   # Sede (Roma, Milano, …)
    hire_date_mashfrog: Mapped[Optional[date]] = mapped_column(Date)      # Data assunzione in MF

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationship 1:1 con CV
    cv: Mapped[Optional["CV"]] = relationship("CV", back_populates="user", uselist=False, cascade="all, delete-orphan")


# ── CV (radice del profilo) ────────────────────────────────────────────────────

class CV(Base):
    __tablename__ = "cvs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)

    # Anagrafica
    birth_date: Mapped[Optional[date]] = mapped_column(Date)
    birth_place: Mapped[Optional[str]] = mapped_column(String(255))
    residence_city: Mapped[Optional[str]] = mapped_column(String(255))

    # Profilo professionale
    title: Mapped[Optional[str]] = mapped_column(String(255))        # es. "Senior Software Engineer"
    summary: Mapped[Optional[str]] = mapped_column(Text)             # bio/sommario
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    linkedin_url: Mapped[Optional[str]] = mapped_column(String(500))

    # Date chiave carriera
    first_employment_date: Mapped[Optional[date]] = mapped_column(Date)   # prima assunzione assoluta

    availability_status: Mapped[AvailabilityStatus] = mapped_column(
        Enum(AvailabilityStatus), default=AvailabilityStatus.DISPONIBILE
    )

    # Metadati
    completeness_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relazioni
    user: Mapped["User"] = relationship("User", back_populates="cv")
    educations: Mapped[List["Education"]] = relationship("Education", back_populates="cv", cascade="all, delete-orphan")
    languages: Mapped[List["Language"]] = relationship("Language", back_populates="cv", cascade="all, delete-orphan")
    roles: Mapped[List["CVRole"]] = relationship("CVRole", back_populates="cv", cascade="all, delete-orphan", order_by="CVRole.start_date.desc()")
    skills: Mapped[List["CVSkill"]] = relationship("CVSkill", back_populates="cv", cascade="all, delete-orphan")
    references: Mapped[List["Reference"]] = relationship("Reference", back_populates="cv", cascade="all, delete-orphan", order_by="Reference.sort_order")
    certifications: Mapped[List["Certification"]] = relationship("Certification", back_populates="cv", cascade="all, delete-orphan")
    documents: Mapped[List["CVDocument"]] = relationship("CVDocument", back_populates="cv", cascade="all, delete-orphan")


# ── Education ─────────────────────────────────────────────────────────────────

class Education(Base):
    __tablename__ = "educations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cv_id: Mapped[int] = mapped_column(Integer, ForeignKey("cvs.id", ondelete="CASCADE"), nullable=False, index=True)
    degree_level: Mapped[Optional[DegreeLevel]] = mapped_column(Enum(DegreeLevel))
    institution: Mapped[str] = mapped_column(String(255), nullable=False)
    field_of_study: Mapped[Optional[str]] = mapped_column(String(255))
    graduation_year: Mapped[Optional[int]] = mapped_column(Integer)
    graduation_date: Mapped[Optional[date]] = mapped_column(Date)     # data esatta se nota
    grade: Mapped[Optional[str]] = mapped_column(String(50))          # es. "110/110", "85/100"
    notes: Mapped[Optional[str]] = mapped_column(Text)

    cv: Mapped["CV"] = relationship("CV", back_populates="educations")


# ── Language ──────────────────────────────────────────────────────────────────

class Language(Base):
    __tablename__ = "languages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cv_id: Mapped[int] = mapped_column(Integer, ForeignKey("cvs.id", ondelete="CASCADE"), nullable=False, index=True)
    language_name: Mapped[str] = mapped_column(String(100), nullable=False)
    level: Mapped[Optional[LanguageLevel]] = mapped_column(Enum(LanguageLevel))

    cv: Mapped["CV"] = relationship("CV", back_populates="languages")

    __table_args__ = (
        UniqueConstraint("cv_id", "language_name", name="uq_cv_language"),
    )


# ── CVRole (ruoli ricoperti nel tempo) ────────────────────────────────────────

class CVRole(Base):
    __tablename__ = "cv_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cv_id: Mapped[int] = mapped_column(Integer, ForeignKey("cvs.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)   # es. "Senior Developer"
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)            # null = ruolo corrente
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    company: Mapped[Optional[str]] = mapped_column(String(255))       # azienda (di solito MF)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    cv: Mapped["CV"] = relationship("CV", back_populates="roles")


# ── CVSkill ───────────────────────────────────────────────────────────────────

class CVSkill(Base):
    __tablename__ = "cv_skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cv_id: Mapped[int] = mapped_column(Integer, ForeignKey("cvs.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category: Mapped[SkillCategory] = mapped_column(Enum(SkillCategory), nullable=False)
    rating: Mapped[Optional[int]] = mapped_column(SmallInteger)       # 1-5 stelle
    notes: Mapped[Optional[str]] = mapped_column(Text)

    cv: Mapped["CV"] = relationship("CV", back_populates="skills")

    __table_args__ = (
        UniqueConstraint("cv_id", "skill_name", "category", name="uq_cv_skill"),
        Index("ix_cv_skills_name_cat", "skill_name", "category"),
    )


# ── Reference (esperienze lavorative / clienti) ───────────────────────────────

class Reference(Base):
    __tablename__ = "references"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cv_id: Mapped[int] = mapped_column(Integer, ForeignKey("cvs.id", ondelete="CASCADE"), nullable=False, index=True)

    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)

    company_name: Mapped[Optional[str]] = mapped_column(String(255))  # società datrice di lavoro
    client_name: Mapped[Optional[str]] = mapped_column(String(255))   # cliente finale
    role: Mapped[Optional[str]] = mapped_column(String(255))          # ruolo svolto nel progetto

    project_description: Mapped[Optional[str]] = mapped_column(Text)
    activities: Mapped[Optional[str]] = mapped_column(Text)           # attività svolte
    skills_acquired: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String))

    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    cv: Mapped["CV"] = relationship("CV", back_populates="references")


# ── Certification ─────────────────────────────────────────────────────────────

class Certification(Base):
    __tablename__ = "certifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cv_id: Mapped[int] = mapped_column(Integer, ForeignKey("cvs.id", ondelete="CASCADE"), nullable=False, index=True)

    year: Mapped[Optional[int]] = mapped_column(Integer)              # anno ottenimento
    issuing_org: Mapped[Optional[str]] = mapped_column(String(255))   # ente certificatore
    cert_code: Mapped[Optional[str]] = mapped_column(String(100))     # codice ufficiale
    name: Mapped[str] = mapped_column(String(500), nullable=False)    # nome/descrizione
    version: Mapped[Optional[str]] = mapped_column(String(50))        # versione (es. "v8", "2022")
    expiry_date: Mapped[Optional[date]] = mapped_column(Date)         # null = non scade
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Collegamento allegato
    doc_attachment_type: Mapped[DocAttachmentType] = mapped_column(
        Enum(DocAttachmentType), default=DocAttachmentType.NONE
    )
    doc_url: Mapped[Optional[str]] = mapped_column(String(1000))      # URL SharePoint / Credly / altro
    has_formal_cert: Mapped[bool] = mapped_column(Boolean, default=True)

    # Credly integration (Sprint 5)
    credly_badge_id: Mapped[Optional[str]] = mapped_column(String(200))    # UUID badge Credly
    badge_image_url: Mapped[Optional[str]] = mapped_column(String(1000))   # URL immagine badge

    cv: Mapped["CV"] = relationship("CV", back_populates="certifications")


# ── CVDocument (upload CV originali → SharePoint) ─────────────────────────────

class CVDocument(Base):
    __tablename__ = "cv_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cv_id: Mapped[int] = mapped_column(Integer, ForeignKey("cvs.id", ondelete="CASCADE"), nullable=False, index=True)

    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    sharepoint_url: Mapped[Optional[str]] = mapped_column(String(1000))   # URL file su SharePoint
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer)

    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    uploaded_by_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))

    parsed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    parse_status: Mapped[str] = mapped_column(String(50), default="pending")  # pending|processing|done|error
    ai_raw_output: Mapped[Optional[dict]] = mapped_column(JSONB)

    cv: Mapped["CV"] = relationship("CV", back_populates="documents")
    uploaded_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[uploaded_by_id])


# ── SkillTaxonomy (tassonomia centralizzata, condivisa tra app) ───────────────

class SkillTaxonomy(Base):
    __tablename__ = "skill_taxonomy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    category: Mapped[Optional[SkillCategory]] = mapped_column(Enum(SkillCategory))
    aliases: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String))
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ── CertCatalog (catalogo certificazioni da Credly SAP/OpenText/Databricks) ───

class CertCatalogEntry(Base):
    """
    Catalogo certificazioni alimentato da Credly (SAP, OpenText) e lista statica
    (Databricks). Usato per autocomplete e suggerimento codici esame.
    Aggiornabile tramite POST /cv/cert-catalog/refresh.
    TODO: esporre il refresh in una sezione Admin UI (Sprint futuro).
    """
    __tablename__ = "cert_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    vendor: Mapped[str] = mapped_column(String(50),  nullable=False, index=True)
    cert_code: Mapped[Optional[str]] = mapped_column(String(200), index=True)
    img_url:   Mapped[Optional[str]] = mapped_column(String(1000))
    credly_id: Mapped[Optional[str]] = mapped_column(String(200), unique=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
