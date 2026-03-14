"""
SharePoint integration — placeholder fino a quando le credenziali saranno fornite.

Variabili .env richieste (future):
  SHAREPOINT_SITE_URL   = https://<tenant>.sharepoint.com/sites/<site>
  SHAREPOINT_TENANT_ID  = <azure-tenant-id>
  SHAREPOINT_CLIENT_ID  = <app-registration-client-id>
  SHAREPOINT_CLIENT_SECRET = <app-registration-secret>
  SHAREPOINT_FOLDER_CV  = /Shared Documents/CV
  SHAREPOINT_FOLDER_CERT = /Shared Documents/Certificazioni
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def upload_cv(filename: str, content: bytes, mime_type: str) -> Optional[str]:
    """
    Carica un file CV su SharePoint e restituisce l'URL pubblico.
    PLACEHOLDER: restituisce None finché le credenziali non sono configurate.
    """
    logger.warning("SharePoint non configurato — upload CV skipped (%s)", filename)
    return None


async def upload_certification(filename: str, content: bytes, mime_type: str) -> Optional[str]:
    """
    Carica un allegato certificazione su SharePoint.
    PLACEHOLDER: restituisce None finché le credenziali non sono configurate.
    """
    logger.warning("SharePoint non configurato — upload cert skipped (%s)", filename)
    return None


def is_configured() -> bool:
    """Restituisce True quando SharePoint è configurato (variabili .env presenti)."""
    from app.database import settings
    return bool(
        getattr(settings, "sharepoint_site_url", None)
        and getattr(settings, "sharepoint_client_id", None)
        and getattr(settings, "sharepoint_client_secret", None)
    )
