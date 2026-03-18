"""
CV Management System — Backend FastAPI
Entry point: lifespan, middleware, router registration, health endpoint.
"""
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base, SessionLocal, settings
from app.models import UserRole  # noqa: F401 — ensure enum registered
from app.seed import seed_data
from app.seed_excel import seed_from_excel

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility()
    os.makedirs(settings.upload_dir, exist_ok=True)
    with SessionLocal() as db:
        seed_data(db)           # crea admin + demo users, poi sync_all_passwords
        seed_from_excel(db)     # crea utenti Excel con PLACEHOLDER_HASH
        from app.seed import _sync_all_passwords
        _sync_all_passwords(db) # ri-sincronizza TUTTI (inclusi quelli appena creati da Excel)
    yield
    # Shutdown (nessuna azione necessaria)


def ensure_schema_compatibility() -> None:
    """
    Migrazioni DDL idempotenti — aggiungere qui colonne/enum mancanti
    senza rompere installazioni esistenti.
    Pattern copiato da IT_RESOURCE_MGMT.
    """
    from sqlalchemy import text
    with engine.connect() as conn:
        # Sprint 5 — Credly badge fields
        conn.execute(text(
            "ALTER TABLE certifications ADD COLUMN IF NOT EXISTS credly_badge_id VARCHAR(200)"
        ))
        conn.execute(text(
            "ALTER TABLE certifications ADD COLUMN IF NOT EXISTS badge_image_url VARCHAR(1000)"
        ))

        # Sprint 6 — uploaded_file_path su certifications
        conn.execute(text(
            "ALTER TABLE certifications ADD COLUMN IF NOT EXISTS uploaded_file_path VARCHAR(1000)"
        ))

        conn.commit()

    # Sprint 6 — nuovi valori AvailabilityStatus
    # ALTER TYPE ADD VALUE richiede AUTOCOMMIT (non può stare in una transazione)
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as ac:
        for val in ("IN_HIRING", "IN_STAFF", "DIMESSO"):
            try:
                ac.execute(text(f"ALTER TYPE availabilitystatus ADD VALUE IF NOT EXISTS '{val}'"))
            except Exception:
                pass  # già presente

    # Sprint 6 — migra vecchi valori → nuovi (connessione separata post-commit enum)
    with engine.connect() as conn3:
        conn3.execute(text(
            "UPDATE cvs SET availability_status = 'IN_STAFF'::availabilitystatus "
            "WHERE availability_status::text IN ('DISPONIBILE', 'OCCUPATO')"
        ))
        conn3.commit()



app = FastAPI(
    title="CV Management System",
    description="API per gestione curriculum aziendali. Fornisce anche API pubbliche per integrazione inter-app.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Router registration ───────────────────────────────────────────────────────
from app.routers import auth  # noqa: E402
app.include_router(auth.router, prefix="/auth", tags=["auth"])

# TODO Sprint 1: users router
# from app.routers import users
# app.include_router(users.router, prefix="/users", tags=["users"])

from app.routers import cv
app.include_router(cv.router, prefix="/cv", tags=["cv"])

# TODO Sprint 2: skills router
# from app.routers import skills
# app.include_router(skills.router, prefix="/skills", tags=["skills"])

from app.routers import upload
app.include_router(upload.router, prefix="/upload", tags=["upload"])

# TODO Sprint 4: search + API pubblica
# from app.routers import search
# app.include_router(search.router, prefix="/api/v1", tags=["public-api"])

from app.routers import export  # noqa: E402
app.include_router(export.router, prefix="/export", tags=["export"])


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "service": "cv-management-backend"}
