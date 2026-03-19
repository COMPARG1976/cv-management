"""
Test upload CV — POST /upload/cv, POST /upload/apply, GET/DELETE /upload/documents.
"""
import io
import pytest
from httpx import AsyncClient

from tests.conftest import USER_EMAIL
import app.excel_store as store

pytestmark = pytest.mark.anyio

# ── Helpers ───────────────────────────────────────────────────────────────────

def _dummy_pdf() -> bytes:
    """PDF minimale valido (1 pagina, nessun contenuto reale)."""
    return b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer<</Size 4/Root 1 0 R>>
startxref
190
%%EOF"""


# ── Lista documenti (inizialmente vuota) ──────────────────────────────────────

async def test_list_documents_empty(user_client: AsyncClient):
    r = await user_client.get("/upload/documents")
    assert r.status_code == 200
    assert r.json() == []


# ── Upload senza AI ───────────────────────────────────────────────────────────

async def test_upload_no_ai(user_client: AsyncClient, monkeypatch):
    """Upload con ai_update=false salva il documento senza chiamare l'AI."""
    # Previeni scrittura su SharePoint / disco
    async def _noop_upload(path, content, _retries=4):
        return ""
    monkeypatch.setattr(store, "_sp_upload", _noop_upload)

    pdf = _dummy_pdf()
    r = await user_client.post(
        "/upload/cv",
        files={"file": ("cv.pdf", io.BytesIO(pdf), "application/pdf")},
        data={"ai_update": "false", "tags_json": '["test"]'},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ai_skipped") is True
    assert "document_id" in body

    # Documento presente in STORE
    docs = store.STORE["documents"].get(USER_EMAIL, [])
    assert len(docs) == 1
    # Tags vengono serializzati come stringa pipe-separated nello STORE (formato Excel)
    # ["test"] → "test"
    assert "test" in docs[0]["tags"]


# ── Upload con tipo non consentito ────────────────────────────────────────────

async def test_upload_invalid_extension(user_client: AsyncClient):
    r = await user_client.post(
        "/upload/cv",
        files={"file": ("photo.jpg", io.BytesIO(b"fake"), "image/jpeg")},
        data={"ai_update": "false"},
    )
    assert r.status_code == 400


# ── Upload file troppo grande ─────────────────────────────────────────────────

async def test_upload_too_large(user_client: AsyncClient):
    big = b"x" * (store.settings.max_upload_size_mb * 1024 * 1024 + 1)
    r = await user_client.post(
        "/upload/cv",
        files={"file": ("cv.pdf", io.BytesIO(big), "application/pdf")},
        data={"ai_update": "false"},
    )
    assert r.status_code == 413


# ── Delete documento ──────────────────────────────────────────────────────────

async def test_delete_document(user_client: AsyncClient, monkeypatch):
    # Prima crea un documento
    async def _noop_upload(path, content, _retries=4):
        return ""
    monkeypatch.setattr(store, "_sp_upload", _noop_upload)

    pdf = _dummy_pdf()
    r = await user_client.post(
        "/upload/cv",
        files={"file": ("cv.pdf", io.BytesIO(pdf), "application/pdf")},
        data={"ai_update": "false"},
    )
    doc_id = r.json()["document_id"]

    # Poi cancella
    r = await user_client.delete(f"/upload/documents/{doc_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "deleted"

    # Non più nello STORE
    docs = store.STORE["documents"].get(USER_EMAIL, [])
    assert not any(d["id"] == doc_id for d in docs)


async def test_delete_nonexistent_document(user_client: AsyncClient):
    r = await user_client.delete("/upload/documents/does-not-exist")
    assert r.status_code == 404


# ── Apply diff (senza AI) ─────────────────────────────────────────────────────

async def test_apply_diff_profile(user_client: AsyncClient, monkeypatch):
    """apply con selezione AI aggiorna il profilo."""
    async def _noop_upload(path, content, _retries=4):
        return ""
    monkeypatch.setattr(store, "_sp_upload", _noop_upload)

    # Carica un documento per avere un doc_id
    pdf = _dummy_pdf()
    r = await user_client.post(
        "/upload/cv",
        files={"file": ("cv.pdf", io.BytesIO(pdf), "application/pdf")},
        data={"ai_update": "false"},
    )
    doc_id = r.json()["document_id"]

    payload = {
        "document_id": doc_id,
        "profile": [{"field": "phone", "db_value": "", "ai_value": "+39 333 0000000", "selected": "ai"}],
        "skills": [],
        "references": [],
        "educations": [],
        "certifications": [],
        "languages": [],
    }
    r = await user_client.post("/upload/apply", json=payload)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert store.STORE["cv_profiles"][USER_EMAIL]["phone"] == "+39 333 0000000"


async def test_apply_diff_adds_skill(user_client: AsyncClient, monkeypatch):
    """apply con skill nuova la aggiunge allo STORE."""
    async def _noop_upload(path, content, _retries=4):
        return ""
    monkeypatch.setattr(store, "_sp_upload", _noop_upload)

    pdf = _dummy_pdf()
    r = await user_client.post(
        "/upload/cv",
        files={"file": ("cv.pdf", io.BytesIO(pdf), "application/pdf")},
        data={"ai_update": "false"},
    )
    doc_id = r.json()["document_id"]

    payload = {
        "document_id": doc_id,
        "profile": [],
        "skills": [{"status": "new", "db": None,
                    "ai": {"skill_name": "Kubernetes", "category": "HARD", "rating": 3},
                    "selected": "ai"}],
        "references": [], "educations": [], "certifications": [], "languages": [],
    }
    r = await user_client.post("/upload/apply", json=payload)
    assert r.status_code == 200
    skills = store.STORE["skills"].get(USER_EMAIL, [])
    assert any(s["skill_name"] == "Kubernetes" for s in skills)
