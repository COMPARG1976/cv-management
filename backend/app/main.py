"""
CV Management System — Backend FastAPI
Entry point: lifespan, middleware, router registration, health endpoint.
"""
import os
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import engine, Base, SessionLocal, settings
from app.models import UserRole  # noqa: F401 — ensure enum registered
from app.seed import seed_data
from app.seed_excel import seed_from_excel

logger = logging.getLogger(__name__)

CATALOG_JSON = os.path.join(os.path.dirname(__file__), "cert_catalog.json")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility()
    os.makedirs(settings.upload_dir, exist_ok=True)
    with SessionLocal() as db:
        seed_data(db)
        seed_from_excel(db)
        populate_cert_catalog(db)
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
        conn.commit()


def populate_cert_catalog(db) -> int:
    """
    Popola la tabella cert_catalog dal file cert_catalog.json.
    Esegue UPSERT su credly_id (se presente) oppure su (name, vendor).
    Restituisce il numero di righe inserite/aggiornate.
    Idempotente: sicuro da chiamare ad ogni avvio.
    """
    from app.models import CertCatalogEntry
    from sqlalchemy import select

    if not os.path.exists(CATALOG_JSON):
        logger.warning("cert_catalog.json non trovato, skip populate.")
        return 0

    with open(CATALOG_JSON, encoding="utf-8") as f:
        entries = json.load(f)

    count = 0
    for e in entries:
        name      = (e.get("name") or "").strip()
        vendor    = (e.get("vendor") or "").strip()
        cert_code = (e.get("cert_code") or "").strip() or None
        img_url   = (e.get("img_url") or "").strip() or None
        credly_id = (e.get("credly_id") or "").strip() or None
        if not name or not vendor:
            continue

        # Cerca per credly_id se disponibile, altrimenti per (name, vendor)
        if credly_id:
            row = db.execute(
                select(CertCatalogEntry).where(CertCatalogEntry.credly_id == credly_id)
            ).scalar_one_or_none()
        else:
            row = db.execute(
                select(CertCatalogEntry).where(
                    CertCatalogEntry.name == name,
                    CertCatalogEntry.vendor == vendor,
                )
            ).scalar_one_or_none()

        if row:
            row.name      = name
            row.cert_code = cert_code
            row.img_url   = img_url
        else:
            db.add(CertCatalogEntry(
                name=name, vendor=vendor,
                cert_code=cert_code, img_url=img_url, credly_id=credly_id,
            ))
        count += 1

    db.commit()
    logger.info("cert_catalog: %d voci sincronizzate.", count)
    return count


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
