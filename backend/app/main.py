"""
CV Management System — Backend FastAPI (Excel backend)
Entry point: lifespan, middleware, router registration, health endpoint.
"""
import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.excel_store as store
from app.excel_store import settings

logger = logging.getLogger(__name__)


_WAL_RETRY_INTERVAL = 30   # secondi tra un retry WAL e il successivo


async def _backup_loop() -> None:
    """Loop periodico che esegue il backup ogni 2 ore."""
    while True:
        await asyncio.sleep(store._BACKUP_INTERVAL_SECONDS)
        try:
            done = await store.do_periodic_backup()
            if done:
                logger.info("Backup periodico completato")
        except Exception as e:
            logger.error(f"Backup periodico errore: {e}")


async def _wal_retry_loop() -> None:
    """Loop WAL: ogni 30s ritenta persist() se ci sono dati non salvati su SharePoint."""
    while True:
        await asyncio.sleep(_WAL_RETRY_INTERVAL)
        try:
            ok = await store.retry_persist_if_dirty()
            if ok and not store._dirty:
                pass   # tutto sincronizzato, nessun log (evita rumore nei log)
        except Exception as e:
            logger.error(f"WAL retry errore: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — carica dati da SharePoint
    try:
        await store.init_store()
        logger.info("STORE inizializzato correttamente")
    except Exception as e:
        logger.error(f"Errore inizializzazione STORE: {e}")

    # Avvia task di background
    backup_task  = asyncio.create_task(_backup_loop())
    wal_task     = asyncio.create_task(_wal_retry_loop())

    yield

    # Shutdown — ferma entrambi i task
    for task in (backup_task, wal_task):
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


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
    return {
        "status": "ok",
        "service": "cv-management-backend",
        "sharepoint_dirty": store._dirty,   # True = dati RAM non ancora su SP
    }
