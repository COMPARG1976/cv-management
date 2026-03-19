"""
Fixtures condivise per i test del CV Management System (Excel backend).

Setup:
  - Carica STORE da tests/fixtures/test_master_cv.xlsx (nessun accesso a SharePoint)
  - Ripristina lo STORE prima e dopo ogni test (isolamento completo)
  - Fornisce token JWT validi per user e admin
  - Fixture `client` usa httpx.AsyncClient contro l'app FastAPI
  - persist() è sostituito con una no-op (nessuna scrittura su disco/SP)

Per rigenerare il file di fixture:
    docker exec cv_mgmt_backend python tests/fixtures/make_test_xlsx.py
"""
import io
from pathlib import Path

import openpyxl
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

import app.excel_store as store
from app.excel_store import STORE
from app.security import create_access_token
from app.main import app

# ─────────────────────────────────────────────────────────────────────────────
# Costanti utenti di test  (corrispondono ai dati in test_master_cv.xlsx)
# ─────────────────────────────────────────────────────────────────────────────
USER_EMAIL  = "test.user@example.com"
ADMIN_EMAIL = "test.admin@example.com"

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "test_master_cv.xlsx"


# ─────────────────────────────────────────────────────────────────────────────
# Caricamento fixture xlsx
# ─────────────────────────────────────────────────────────────────────────────

def _load_fixture_xlsx() -> None:
    """Carica il file xlsx di test in STORE tramite _wb_to_store (zero SharePoint)."""
    if not _FIXTURE_PATH.exists():
        # Genera al volo se il file non c'è ancora
        from tests.fixtures.make_test_xlsx import build_xlsx
        _FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _FIXTURE_PATH.write_bytes(build_xlsx())

    content = _FIXTURE_PATH.read_bytes()
    wb = openpyxl.load_workbook(io.BytesIO(content))
    # Svuota STORE prima di ricaricare
    for k in ("users","cv_profiles","skills","educations","experiences",
              "certifications","languages","documents"):
        STORE[k] = {}
    STORE["ref_bu"] = STORE["ref_certtags"] = STORE["ref_skills"] = []
    store._wb_to_store(wb)
    store._initialized = True   # evita che init_store() sovrascriva con SP


def _make_token(email: str, role: str) -> str:
    return create_access_token({"sub": email, "role": role, "full_name": "Test"})


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_store():
    """
    Carica lo STORE dal file xlsx di test prima di ogni test.
    Garantisce isolamento completo: ogni test parte da un STORE identico.
    """
    _load_fixture_xlsx()
    yield
    # Pulizia dopo il test (opzionale ma esplicita)
    for k in ("users","cv_profiles","skills","educations","experiences",
              "certifications","languages","documents"):
        STORE[k] = {}
    STORE["ref_bu"] = STORE["ref_certtags"] = STORE["ref_skills"] = []
    store._initialized = False


@pytest_asyncio.fixture(autouse=True)
async def noop_persist(monkeypatch):
    """Sostituisce persist() con no-op: nessuna scrittura su SharePoint/disco."""
    async def _noop():
        pass
    monkeypatch.setattr(store, "persist", _noop)


@pytest.fixture
def user_token() -> str:
    return _make_token(USER_EMAIL, "USER")


@pytest.fixture
def admin_token() -> str:
    return _make_token(ADMIN_EMAIL, "ADMIN")


@pytest_asyncio.fixture
async def client():
    """AsyncClient connesso all'app FastAPI senza I/O reale."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def user_client(client, user_token):
    """Client già autenticato come utente normale."""
    client.headers.update({"Authorization": f"Bearer {user_token}"})
    return client


@pytest_asyncio.fixture
async def admin_client(client, admin_token):
    """Client già autenticato come admin."""
    client.headers.update({"Authorization": f"Bearer {admin_token}"})
    return client
