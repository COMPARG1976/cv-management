"""
Router /export — Sprint 5 (Excel backend).
GET /export/templates    → lista template disponibili in templates/docx/
GET /export/cv/docx      → genera e scarica il CV come Word
"""
import copy
import io
import json
import os
from pathlib import Path
from typing import Optional

import httpx
from docxtpl import DocxTemplate
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

import app.excel_store as store
from app.excel_store import settings
from app.deps import get_current_user

router = APIRouter()

TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "docx"


# ── Costante cartella template SharePoint ────────────────────────────────────
SP_TEMPLATES_FOLDER = "CV_TEMPLATE_JINJA"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_template_meta(filename: str, source: str = "disk") -> Optional[dict]:
    """
    Estrae metadati da un nome file Template_<LANG>_*.docx.
    Ritorna None se il formato non è valido.
    """
    if not filename.endswith(".docx") or not filename.startswith("Template_"):
        return None
    parts = filename[:-5].split("_")   # rimuove .docx poi splitta
    if len(parts) < 3:
        return None
    lang = parts[1].upper()            # IT | EN
    display = " ".join(parts[2:])
    return {
        "filename":     filename,
        "language":     lang,
        "display_name": display,
        "label":        f"[{lang}] {display}",
        "source":       source,        # "disk" | "sharepoint"
    }


def _list_templates_on_disk() -> list:
    """Scansiona TEMPLATES_DIR e restituisce i template validi Template_<LANG>_*.docx."""
    result = []
    if not TEMPLATES_DIR.exists():
        return result
    for f in sorted(TEMPLATES_DIR.iterdir()):
        meta = _parse_template_meta(f.name, source="disk")
        if meta:
            result.append(meta)
    return result


async def _list_templates_sp() -> list:
    """Lista i template dalla cartella SharePoint CV_TEMPLATE_JINJA."""
    files = await store._sp_list_folder(SP_TEMPLATES_FOLDER)
    result = []
    for f in files:
        meta = _parse_template_meta(f["name"], source="sharepoint")
        if meta:
            result.append(meta)
    return result


async def _list_all_templates() -> list:
    """
    Combina template da SharePoint (priorità) e cartella locale.
    Se SharePoint restituisce almeno 1 template, usa solo SharePoint.
    Fallback su disco se SharePoint non disponibile.
    """
    sp_templates = await _list_templates_sp()
    if sp_templates:
        return sp_templates
    return _list_templates_on_disk()


async def _load_template_bytes(template_meta: dict) -> bytes:
    """
    Carica il file .docx del template.
    Se source == "sharepoint" → scarica da SP.
    Se source == "disk" → legge da TEMPLATES_DIR.
    """
    if template_meta.get("source") == "sharepoint":
        content = await store.sp_download_file(SP_TEMPLATES_FOLDER, template_meta["filename"])
        if content:
            return content
        # Se SP fallisce, prova disco come fallback
    # Disco locale
    local = TEMPLATES_DIR / template_meta["filename"]
    if local.exists():
        return local.read_bytes()
    raise HTTPException(404, f"Template '{template_meta['filename']}' non trovato né su SharePoint né su disco")


def _sort_refs(refs: list) -> list:
    """end_date DESC NULLS FIRST → start_date DESC."""
    def key(r):
        end   = (r.get("end_date")   or "9999-99")[:7]
        start = (r.get("start_date") or "")[:7]
        return (end, start)
    return sorted(refs, key=key, reverse=True)


def _fmt_date(d: Optional[str]) -> Optional[str]:
    """'YYYY-MM-DD' → 'MM/YYYY' oppure None."""
    if not d:
        return None
    try:
        parts = str(d).strip().split("-")
        if len(parts) >= 2:
            return f"{parts[1]}/{parts[0]}"
        return str(d)
    except Exception:
        return str(d)


def _rating_stars(rating) -> str:
    """1-5 → stringa ★★★★☆."""
    if not rating:
        return ""
    r = max(0, min(5, int(rating)))
    return "★" * r + "☆" * (5 - r)


def _build_context(email: str) -> dict:
    """
    Costruisce il contesto Jinja2 con tutti i campi e alias per compatibilità
    tra Template_IT_Standard, Template_EN_Standard e Template_IT_Esempio.
    """
    user = store.STORE["users"].get(email, {})
    cv = store.STORE["cv_profiles"].get(email, {})

    # ── Esperienze ────────────────────────────────────────────────────────────
    refs = store.STORE["experiences"].get(email, [])
    sorted_refs = _sort_refs(refs)
    experiences = []
    for ref in sorted_refs:
        start_fmt = _fmt_date(ref.get("start_date")) or ""
        end_fmt   = _fmt_date(ref.get("end_date"))
        experiences.append({
            "company":             ref.get("company_name") or "",
            "company_name":        ref.get("company_name") or "",
            "client_name":         ref.get("client_name")  or "",
            "role":                ref.get("role")          or "",
            "start_date":          start_fmt,
            "start_date_fmt":      start_fmt,
            "end_date_fmt":        end_fmt,
            "project_description": ref.get("project_description") or "",
            "activities":          ref.get("activities")    or "",
            "skills_csv":          "",
            "skills_acquired":     [],
        })

    # ── Competenze ────────────────────────────────────────────────────────────
    skills_hard, skills_soft = [], []
    for sk in sorted(store.STORE["skills"].get(email, []), key=lambda x: x.get("skill_name", "")):
        entry = {
            "skill_name":   sk.get("skill_name", ""),
            "name":         sk.get("skill_name", ""),
            "category":     sk.get("category", ""),
            "rating":       sk.get("rating") or 0,
            "rating_stars": _rating_stars(sk.get("rating")),
        }
        if sk.get("category") == "HARD":
            skills_hard.append(entry)
        else:
            skills_soft.append(entry)

    # ── Formazione ────────────────────────────────────────────────────────────
    educations = [
        {
            "institution":     edu.get("institution", ""),
            "degree_level":    edu.get("degree_level") or "",
            "degree_type":     edu.get("degree_level") or "",
            "field_of_study":  edu.get("field_of_study") or "",
            "graduation_year": edu.get("graduation_year") or "",
            "end_year":        edu.get("graduation_year") or "",
            "start_year":      "",
            "grade":           edu.get("grade") or "",
            "notes":           edu.get("notes") or "",
        }
        for edu in sorted(
            store.STORE["educations"].get(email, []),
            key=lambda e: int(e["graduation_year"]) if e.get("graduation_year") and str(e.get("graduation_year", "")).isdigit() else 9999
        )
    ]

    # ── Lingue ────────────────────────────────────────────────────────────────
    languages = [
        {
            "language_name": lang.get("language_name", ""),
            "language":      lang.get("language_name", ""),
            "level":         lang.get("level") or "",
            "notes":         "",
        }
        for lang in store.STORE["languages"].get(email, [])
    ]

    # ── Certificazioni ────────────────────────────────────────────────────────
    certifications = [
        {
            "name":        cert.get("name", ""),
            "cert_code":   cert.get("cert_code")   or "",
            "issuing_org": cert.get("issuing_org") or "",
            "year":        cert.get("year")        or "",
            "issue_date":  cert.get("year")        or "",
            "expiry_date": _fmt_date(cert.get("expiry_date")) or "",
            "version":     cert.get("version")     or "",
            "doc_url":     cert.get("doc_url")     or "",
        }
        for cert in sorted(
            store.STORE["certifications"].get(email, []),
            key=lambda x: -(int(x["year"]) if x.get("year") and str(x.get("year", "")).isdigit() else 0)
        )
    ]

    return {
        "full_name":          user.get("full_name") or "",
        "email":              email,
        "job_title":          cv.get("title") or "",
        "phone":              cv.get("phone") or "",
        "linkedin_url":       cv.get("linkedin_url") or "",
        "location":           cv.get("residence_city") or "",
        "residence_city":     cv.get("residence_city") or "",
        "birth_date":         _fmt_date(cv.get("birth_date")) or "",
        "summary":            cv.get("summary") or "",
        "hire_date_mashfrog": _fmt_date(user.get("hire_date_mashfrog")) or "",
        "mashfrog_office":    user.get("mashfrog_office") or "",
        "bu_mashfrog":        user.get("bu_mashfrog") or "",
        "experiences":        experiences,
        "skills_hard":        skills_hard,
        "skills_soft":        skills_soft,
        "skills":             skills_hard + skills_soft,
        "educations":         educations,
        "languages":          languages,
        "certifications":     certifications,
    }


async def _translate_to_english(context: dict, api_key: str) -> dict:
    """Traduce in inglese i campi testuali tramite OpenAI gpt-4o-mini."""
    to_translate: dict = {}

    if context.get("summary"):
        to_translate["summary"] = context["summary"]
    if context.get("job_title"):
        to_translate["job_title"] = context["job_title"]
    for i, exp in enumerate(context.get("experiences", [])):
        if exp.get("project_description"):
            to_translate[f"exp_{i}_pd"] = exp["project_description"]
        if exp.get("activities"):
            to_translate[f"exp_{i}_act"] = exp["activities"]

    if not to_translate:
        return context

    prompt = (
        "Translate the following Italian professional CV texts to English. "
        "Return a JSON object with the same keys and English values. "
        "Keep technical terms, product names, company names, acronyms as-is.\n\n"
        + json.dumps(to_translate, ensure_ascii=False)
    )

    async with httpx.AsyncClient(timeout=45) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type":  "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
            },
        )
    if resp.status_code != 200:
        raise HTTPException(502, f"Traduzione AI fallita: {resp.text[:200]}")

    translated = json.loads(resp.json()["choices"][0]["message"]["content"])
    ctx = copy.deepcopy(context)
    if "summary"   in translated: ctx["summary"]   = translated["summary"]
    if "job_title" in translated: ctx["job_title"] = translated["job_title"]
    for i, exp in enumerate(ctx.get("experiences", [])):
        if f"exp_{i}_pd"  in translated:
            exp["project_description"] = translated[f"exp_{i}_pd"]
        if f"exp_{i}_act" in translated:
            exp["activities"] = translated[f"exp_{i}_act"]
    return ctx


# ── Mock context per validazione ──────────────────────────────────────────────

def _build_mock_context() -> dict:
    """Contesto minimo con tutti i campi attesi dai template Jinja2.
    Usato per validare la sintassi senza dati reali.
    Liste con un elemento fittizio così i loop {%- for x in list %} vengono eseguiti.
    """
    mock_exp = {
        "company": "Azienda Srl", "company_name": "Azienda Srl",
        "client_name": "Cliente SpA", "role": "Sviluppatore",
        "start_date": "01/2020", "start_date_fmt": "01/2020",
        "end_date_fmt": "12/2023",
        "project_description": "Descrizione progetto di test.",
        "activities": "Attività di test.", "skills_csv": "Python, SQL",
        "skills_acquired": ["Python"],
    }
    mock_skill = {
        "skill_name": "Python", "name": "Python",
        "category": "HARD", "rating": 4, "rating_stars": "★★★★☆",
    }
    mock_edu = {
        "institution": "Università Test", "degree_level": "LAUREA_MAGISTRALE",
        "degree_type": "LAUREA_MAGISTRALE", "field_of_study": "Informatica",
        "graduation_year": "2015", "end_year": "2015",
        "start_year": "2013", "grade": "110/110", "notes": "",
    }
    mock_lang = {
        "language_name": "Inglese", "language": "Inglese",
        "level": "C1", "notes": "",
    }
    mock_cert = {
        "name": "Certificazione Test", "cert_code": "TEST-001",
        "issuing_org": "Ente Test", "year": "2022",
        "issue_date": "2022", "expiry_date": "12/2025",
        "version": "1.0", "doc_url": "",
    }
    return {
        "full_name": "Mario Rossi", "email": "mario.rossi@test.com",
        "job_title": "Senior Developer", "phone": "+39 333 1234567",
        "linkedin_url": "https://linkedin.com/in/mario-rossi",
        "location": "Milano", "residence_city": "Milano",
        "birth_date": "01/1985", "summary": "Sviluppatore esperto con 10 anni di esperienza.",
        "hire_date_mashfrog": "03/2020", "mashfrog_office": "Milano",
        "bu_mashfrog": "Technology",
        "experiences":    [mock_exp],
        "skills_hard":    [mock_skill],
        "skills_soft":    [mock_skill],
        "skills":         [mock_skill],
        "educations":     [mock_edu],
        "languages":      [mock_lang],
        "certifications": [mock_cert],
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/templates")
async def list_templates():
    """Lista i template disponibili da SharePoint CV_TEMPLATE_JINJA (fallback: cartella locale)."""
    return {"templates": await _list_all_templates()}


@router.get("/templates/validate")
async def validate_templates(current_user: dict = Depends(get_current_user)):
    """Scarica e valida ogni template Jinja2: struttura DOCX + sintassi + render mock.

    Per ogni template restituisce:
      status  : "ok" | "error"
      checks  : lista di step superati/falliti
      error   : messaggio di errore (se status=error)
    """
    templates = await _list_all_templates()
    mock_ctx  = _build_mock_context()
    results   = []

    for tmpl_meta in templates:
        entry = {
            "filename": tmpl_meta["filename"],
            "source":   tmpl_meta.get("source", "?"),
            "status":   "ok",
            "checks":   [],
            "error":    None,
        }

        # Step 1 — scarica il file
        try:
            tpl_bytes = await _load_template_bytes(tmpl_meta)
            entry["checks"].append("✅ File scaricato")
        except Exception as e:
            entry["status"] = "error"
            entry["error"]  = f"Download fallito: {e}"
            entry["checks"].append("❌ Download fallito")
            results.append(entry)
            continue

        # Step 2 — struttura DOCX valida
        try:
            tpl = DocxTemplate(io.BytesIO(tpl_bytes))
            entry["checks"].append("✅ DOCX valido")
        except Exception as e:
            entry["status"] = "error"
            entry["error"]  = f"DOCX non valido: {e}"
            entry["checks"].append("❌ DOCX non valido")
            results.append(entry)
            continue

        # Step 3 — render con contesto mock (verifica sintassi Jinja2 + variabili)
        try:
            tpl.render(mock_ctx, autoescape=False)
            entry["checks"].append("✅ Render Jinja2 OK")
        except Exception as e:
            entry["status"] = "error"
            entry["error"]  = f"Errore Jinja2: {str(e)[:300]}"
            entry["checks"].append(f"❌ Render Jinja2 fallito")

        results.append(entry)

    ok_count  = sum(1 for r in results if r["status"] == "ok")
    err_count = sum(1 for r in results if r["status"] == "error")
    return {
        "total":     len(results),
        "ok":        ok_count,
        "errors":    err_count,
        "templates": results,
    }


@router.get("/cv/docx")
async def export_cv_docx(
    template: str = Query(..., description="Nome file template es. Template_IT_Standard_Mashfrog_v1.docx"),
    current_user: dict = Depends(get_current_user),
):
    """Genera e scarica il CV dell'utente autenticato in formato Word."""
    if ".." in template or not template.startswith("Template_") or not template.endswith(".docx"):
        raise HTTPException(400, "Nome template non valido")

    email = current_user["email"]

    # Recupera metadati template (SP o disco)
    all_tpls = await _list_all_templates()
    tmpl_meta = next((t for t in all_tpls if t["filename"] == template), None)
    if not tmpl_meta:
        raise HTTPException(404, f"Template '{template}' non trovato")

    parts    = template.split("_")
    language = parts[1].upper() if len(parts) > 1 else "IT"

    context = _build_context(email)

    if language == "EN":
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise HTTPException(500, "OPENAI_API_KEY non configurata — impossibile tradurre")
        context = await _translate_to_english(context, api_key)

    # Carica bytes template (SP o disco)
    tpl_bytes = await _load_template_bytes(tmpl_meta)
    tpl = DocxTemplate(io.BytesIO(tpl_bytes))
    tpl.render(context)

    output = io.BytesIO()
    tpl.save(output)
    output.seek(0)

    user_slug  = (current_user.get("full_name") or "cv").replace(" ", "_")
    tmpl_slug  = template.replace(".docx", "").replace("Template_IT_", "").replace("Template_EN_", "")
    filename   = f"CV_{user_slug}_{tmpl_slug}.docx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
