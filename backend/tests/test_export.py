"""
Test export — GET /export/templates, GET /export/cv/docx.
"""
import io
import pytest
from pathlib import Path
from httpx import AsyncClient

from tests.conftest import USER_EMAIL
import app.excel_store as store
from app.routers.export import (
    _parse_template_meta, _list_templates_on_disk,
    _build_context, _sort_refs, _fmt_date, _rating_stars,
)

pytestmark = pytest.mark.anyio


# ── Helpers unitari ───────────────────────────────────────────────────────────

def test_parse_template_meta_valid():
    meta = _parse_template_meta("Template_IT_Standard_Mashfrog_v1.docx")
    assert meta is not None
    assert meta["language"] == "IT"
    assert meta["display_name"] == "Standard Mashfrog v1"
    assert meta["filename"] == "Template_IT_Standard_Mashfrog_v1.docx"


def test_parse_template_meta_en():
    meta = _parse_template_meta("Template_EN_Standard_v2.docx", source="sharepoint")
    assert meta["language"] == "EN"
    assert meta["source"] == "sharepoint"


def test_parse_template_meta_invalid():
    assert _parse_template_meta("random_file.docx") is None
    assert _parse_template_meta("Template_IT.docx") is None    # < 3 parts
    assert _parse_template_meta("Template_IT_foo.txt") is None  # wrong ext


def test_fmt_date():
    assert _fmt_date("2023-06-15") == "06/2023"
    assert _fmt_date("2020-12") == "12/2020"
    assert _fmt_date(None) is None
    assert _fmt_date("") is None


def test_rating_stars():
    assert _rating_stars(3) == "★★★☆☆"
    assert _rating_stars(5) == "★★★★★"
    # 0 è falsy → la funzione ritorna "" (non rappresenta stelle vuote)
    assert _rating_stars(0) == ""
    assert _rating_stars(None) == ""
    # Stringa "3" → deve funzionare tramite int()
    assert _rating_stars(int("3")) == "★★★☆☆"


def test_sort_refs():
    refs = [
        {"company_name": "A", "start_date": "2020-01-01", "end_date": "2022-06-01"},
        {"company_name": "B", "start_date": "2021-01-01", "end_date": None},   # corrente
        {"company_name": "C", "start_date": "2019-01-01", "end_date": "2021-01-01"},
    ]
    sorted_r = _sort_refs(refs)
    # B (corrente, end=None → "9999-99") deve essere prima
    assert sorted_r[0]["company_name"] == "B"
    # A (end 2022) prima di C (end 2021)
    assert sorted_r[1]["company_name"] == "A"
    assert sorted_r[2]["company_name"] == "C"


def test_cert_sort_string_year():
    """Verifica che year stringa non causi TypeError nel sort."""
    store.STORE["certifications"][USER_EMAIL] = [
        {"id": "1", "name": "CertA", "issuing_org": "Org", "year": "2023",
         "cert_code": "", "expiry_date": None, "version": "", "doc_url": ""},
        {"id": "2", "name": "CertB", "issuing_org": "Org", "year": "2020",
         "cert_code": "", "expiry_date": None, "version": "", "doc_url": ""},
    ]
    # Non deve sollevare eccezioni
    ctx = _build_context(USER_EMAIL)
    assert ctx["certifications"][0]["name"] == "CertA"   # 2023 > 2020


def test_education_sort_string_year():
    """Verifica che graduation_year stringa non causi TypeError nel sort."""
    store.STORE["educations"][USER_EMAIL] = [
        {"id": "1", "institution": "Uni A", "degree_level": "LAUREA_MAGISTRALE",
         "field_of_study": "Info", "graduation_year": "2018", "grade": "", "notes": ""},
        {"id": "2", "institution": "Uni B", "degree_level": "DIPLOMA",
         "field_of_study": "Lic", "graduation_year": "2013", "grade": "", "notes": ""},
    ]
    ctx = _build_context(USER_EMAIL)
    assert ctx["educations"][0]["institution"] == "Uni B"   # 2013 < 2018


# ── Build context ─────────────────────────────────────────────────────────────

def test_build_context_structure():
    ctx = _build_context(USER_EMAIL)
    required = ["full_name", "email", "job_title", "experiences",
                "skills_hard", "skills_soft", "educations", "languages", "certifications"]
    for key in required:
        assert key in ctx, f"Manca chiave: {key}"
    assert ctx["email"] == USER_EMAIL
    assert ctx["full_name"] == "Test User"


def test_build_context_skills_split():
    """skills HARD e SOFT vengono separati correttamente."""
    store.STORE["skills"][USER_EMAIL] = [
        {"id": "s1", "skill_name": "Python", "category": "HARD", "rating": 4},
        {"id": "s2", "skill_name": "Comunicazione", "category": "SOFT", "rating": 3},
    ]
    ctx = _build_context(USER_EMAIL)
    assert len(ctx["skills_hard"]) == 1
    assert len(ctx["skills_soft"]) == 1
    assert ctx["skills_hard"][0]["skill_name"] == "Python"


# ── Endpoint /export/templates ────────────────────────────────────────────────

async def test_list_templates_endpoint_no_sp(user_client: AsyncClient, monkeypatch):
    """Senza SharePoint restituisce template da disco (lista vuota se cartella non esiste)."""
    # Mock SP list → vuota
    async def _empty_list(folder):
        return []
    monkeypatch.setattr(store, "_sp_list_folder", _empty_list)

    r = await user_client.get("/export/templates")
    assert r.status_code == 200
    data = r.json()
    assert "templates" in data
    assert isinstance(data["templates"], list)


async def test_list_templates_from_sp(user_client: AsyncClient, monkeypatch):
    """Se SP ritorna file, vengono inclusi nella lista template."""
    async def _mock_list(folder):
        return [
            {"name": "Template_IT_Standard_Test_v1.docx", "size": 1000,
             "lastModifiedDateTime": "2025-01-01T00:00:00Z"},
        ]
    monkeypatch.setattr(store, "_sp_list_folder", _mock_list)

    r = await user_client.get("/export/templates")
    assert r.status_code == 200
    templates = r.json()["templates"]
    assert len(templates) == 1
    assert templates[0]["filename"] == "Template_IT_Standard_Test_v1.docx"
    assert templates[0]["source"] == "sharepoint"


# ── Endpoint /export/cv/docx ──────────────────────────────────────────────────

async def test_export_cv_docx_not_found(user_client: AsyncClient, monkeypatch):
    """Template inesistente → 404."""
    async def _empty_list(folder):
        return []
    monkeypatch.setattr(store, "_sp_list_folder", _empty_list)

    r = await user_client.get("/export/cv/docx?template=Template_IT_NonEsiste_v1.docx")
    assert r.status_code == 404


async def test_export_cv_docx_invalid_name(user_client: AsyncClient):
    """Nome template con path traversal → 400."""
    r = await user_client.get("/export/cv/docx?template=../secrets.docx")
    assert r.status_code == 400


async def test_export_cv_docx_with_template(user_client: AsyncClient, monkeypatch, tmp_path):
    """Se il template esiste su disco, genera il DOCX correttamente."""
    # Crea un template .docx minimale con docxtpl
    try:
        from docxtpl import DocxTemplate
        from docx import Document as _DocxDoc
    except ImportError:
        pytest.skip("docxtpl/python-docx non disponibili")

    # Crea template vuoto
    tmpl_dir = tmp_path / "docx"
    tmpl_dir.mkdir()
    tpl_path = tmpl_dir / "Template_IT_Test_v1.docx"
    doc = _DocxDoc()
    doc.add_paragraph("Nome: {{full_name}}")
    doc.save(str(tpl_path))

    # Patch TEMPLATES_DIR
    import app.routers.export as exp_module
    monkeypatch.setattr(exp_module, "TEMPLATES_DIR", tmpl_dir)

    # Mock SP → vuota, usa disco
    async def _empty_list(folder):
        return []
    monkeypatch.setattr(store, "_sp_list_folder", _empty_list)

    r = await user_client.get("/export/cv/docx?template=Template_IT_Test_v1.docx")
    assert r.status_code == 200
    assert "application/vnd.openxmlformats" in r.headers["content-type"]
    assert len(r.content) > 0
