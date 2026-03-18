"""
SharePoint / Microsoft Graph API — Application flow (client credentials).

Il backend usa le proprie credenziali (client_id + client_secret) per chiamare
Graph API. Gli utenti non hanno bisogno di accesso diretto al sito SharePoint.

Struttura cartelle nel drive:
  {drive_name}/
  └── {root_folder}/                       es. STAFF_DATA_AND_DOCUMENTS/
      └── {user_email}/
          ├── CV/
          └── Certificazioni/

Prefisso usato in Certification.uploaded_file_path:
  "sp:STAFF_DATA_AND_DOCUMENTS/mario@mashfrog.com/Certificazioni/cert_5.pdf"

Fallback automatico su storage locale se sharepoint_enabled = False.
"""

import time
import re
import logging
from urllib.parse import urlparse
from typing import Optional

import httpx

from app.database import settings

logger = logging.getLogger(__name__)

# ── Token cache in memoria ─────────────────────────────────────────────────────
_token_cache: dict = {"token": None, "expires_at": 0.0}

# ── Drive ID cache (stabile, cambia solo se la Document Library viene rinominata)
_drive_id_cache: Optional[str] = None


def _parse_site(url: str) -> tuple[str, str]:
    """
    Ricava (host, site_path) dalla SHAREPOINT_SITE_URL.
    Es: https://mashfroggroup.sharepoint.com/sites/ENT_SOLUTION_M4P_STAFF
        -> ("mashfroggroup.sharepoint.com", "/sites/ENT_SOLUTION_M4P_STAFF")
    """
    parsed = urlparse(url)
    return parsed.netloc, parsed.path


async def _get_token() -> str:
    """Restituisce un token Graph API valido, richiedendone uno nuovo se scaduto."""
    now = time.time()
    if _token_cache["token"] and now < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    tenant = settings.entra_tenant_id
    url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, data={
            "client_id":     settings.entra_client_id,
            "client_secret": settings.entra_client_secret,
            "scope":         "https://graph.microsoft.com/.default",
            "grant_type":    "client_credentials",
        })
        resp.raise_for_status()
        data = resp.json()

    _token_cache["token"]      = data["access_token"]
    _token_cache["expires_at"] = now + data.get("expires_in", 3600)
    logger.info("SharePoint: nuovo token Graph API acquisito")
    return _token_cache["token"]


async def _get_drive_id() -> str:
    """
    Trova il drive ID della Document Library configurata (es. "Documenti").
    Con Sites.Selected il formato path-URL non funziona per /drives: bisogna
    prima risolvere il site ID e poi usarlo per listare i drive.
    Il risultato e' cachato per tutta la durata del processo.
    """
    global _drive_id_cache
    if _drive_id_cache:
        return _drive_id_cache

    token = await _get_token()
    host, site_path = _parse_site(settings.sharepoint_site_url)
    drive_name = settings.sharepoint_drive_name

    async with httpx.AsyncClient(timeout=15) as client:
        # Step 1: ottieni il site ID dal path URL (funziona con Sites.Selected)
        site_resp = await client.get(
            f"https://graph.microsoft.com/v1.0/sites/{host}:{site_path}",
            headers={"Authorization": f"Bearer {token}"},
        )
        site_resp.raise_for_status()
        site_id = site_resp.json()["id"]
        logger.info(f"SharePoint: site_id={site_id[:30]}...")

        # Step 2: lista i drive usando il site ID numerico
        resp = await client.get(
            f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        drives = resp.json().get("value", [])

    for d in drives:
        if d.get("name") == drive_name:
            _drive_id_cache = d["id"]
            logger.info(f"SharePoint: drive '{drive_name}' trovato (id={_drive_id_cache[:12]}...)")
            return _drive_id_cache

    available = [d.get("name") for d in drives]
    raise ValueError(
        f"Drive '{drive_name}' non trovato nel sito SharePoint. "
        f"Librerie disponibili: {available}"
    )


def _sp_path(user_email: str, subfolder: str, filename: str) -> str:
    """
    Costruisce il path relativo alla root del drive.
    Es: STAFF_DATA_AND_DOCUMENTS/mario@mashfrog.com/Certificazioni/cert_5.pdf
    """
    root = settings.sharepoint_root_folder
    safe_email = re.sub(r'[<>:"/\\|?*]', "_", user_email)
    return f"{root}/{safe_email}/{subfolder}/{filename}"


async def upload_cv_file(
    user_email: str,
    doc_id: int,
    original_filename: str,
    content: bytes,
) -> str:
    """
    Carica un file CV su SharePoint nella cartella CV dell'utente.
    Ritorna il path relativo nel drive (senza prefisso 'sp:').
    """
    ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else "bin"
    safe_name = f"cv_{doc_id}.{ext}"
    path = _sp_path(user_email, "CV", safe_name)

    token    = await _get_token()
    drive_id = await _get_drive_id()

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.put(
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{path}:/content",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type":  "application/octet-stream",
            },
            content=content,
        )
        resp.raise_for_status()

    logger.info(f"SharePoint: CV caricato -> {path}")
    return path


async def upload_cert_file(
    user_email: str,
    cert_id: int,
    original_filename: str,
    content: bytes,
) -> str:
    """
    Carica un file certificato su SharePoint.
    Ritorna il path relativo nel drive (senza prefisso 'sp:').
    Crea automaticamente le cartelle intermedie se non esistono (Graph lo fa in automatico).
    """
    ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else "bin"
    safe_name = f"cert_{cert_id}.{ext}"
    path = _sp_path(user_email, "Certificazioni", safe_name)

    token    = await _get_token()
    drive_id = await _get_drive_id()

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.put(
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{path}:/content",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type":  "application/octet-stream",
            },
            content=content,
        )
        resp.raise_for_status()

    logger.info(f"SharePoint: file caricato -> {path}")
    return path


async def get_download_url(sp_path: str) -> str:
    """
    Restituisce un URL di download pre-firmato (valido ~1h) per un file SharePoint.
    sp_path: path relativo alla root del drive (senza 'sp:').
    """
    token    = await _get_token()
    drive_id = await _get_drive_id()

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{sp_path}:",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        data = resp.json()

    url = data.get("@microsoft.graph.downloadUrl")
    if not url:
        raise ValueError("URL di download non disponibile per questo file")
    return url


async def delete_file(sp_path: str) -> None:
    """
    Elimina un file da SharePoint. Non fallisce se il file non esiste (404 ok).
    sp_path: path relativo alla root del drive (senza 'sp:').
    """
    token    = await _get_token()
    drive_id = await _get_drive_id()

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.delete(
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{sp_path}:",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code not in (204, 404):
            resp.raise_for_status()

    logger.info(f"SharePoint: file eliminato -> {sp_path}")


async def verify_connection() -> dict:
    """
    Health-check: verifica token + accesso al drive.
    Chiamato all'avvio del backend per segnalare configurazioni errate.
    """
    try:
        await _get_token()
        drive_id = await _get_drive_id()
        return {"ok": True, "drive_id": drive_id[:12] + "..."}
    except Exception as e:
        return {"ok": False, "error": str(e)}
