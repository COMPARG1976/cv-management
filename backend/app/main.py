"""
CV Management System — Backend FastAPI (Excel backend)
Entry point: lifespan, middleware, router registration, health endpoint.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.excel_store as store
from app.excel_store import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — carica dati da SharePoint (o file locale)
    try:
        await store.init_store()
        logger.info("STORE inizializzato correttamente")
    except Exception as e:
        logger.error(f"Errore inizializzazione STORE: {e}")
        # Avvia comunque — lo STORE sarà vuoto, gli endpoint gestiscono casi empty

    yield
    # Shutdown — nessuna azione necessaria (tutti i write sono già persistiti)


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
from app.routers import auth
app.include_router(auth.router, prefix="/auth", tags=["auth"])

from app.routers import users
app.include_router(users.router, prefix="/users", tags=["users"])

from app.routers import cv
app.include_router(cv.router, prefix="/cv", tags=["cv"])

from app.routers import skills
app.include_router(skills.router, prefix="/skills", tags=["skills"])

from app.routers import upload
app.include_router(upload.router, prefix="/upload", tags=["upload"])

from app.routers import search
app.include_router(search.router, prefix="/api/v1", tags=["public-api"])

from app.routers import export
app.include_router(export.router, prefix="/export", tags=["export"])


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "service": "cv-management-backend"}
