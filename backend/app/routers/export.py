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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _list_templates_on_disk() -> list:
    """Scansiona TEMPLATES_DIR e restituisce i template validi Template_<LANG>_*.docx."""
    result = []
    if not TEMPLATES_DIR.exists():
        return result
    for f in sorted(TEMPLATES_DIR.iterdir()):
        if f.suffix != ".docx" or not f.name.startswith("Template_"):
            continue
        parts = f.stem.split("_")   # Template_IT_Standard_Mashfrog_v1
        if len(parts) < 3:
            continue
        lang = parts[1].upper()     # IT | EN
        display = " ".join(parts[2:])
        result.append({
            "filename":     f.name,
            "language":     lang,
            "display_name": display,
            "label":        f"[{lang}] {display}",
        })
    return result


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
            key=lambda e: e.get("graduation_year") or 9999
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
            key=lambda x: -(x.get("year") or 0)
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


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/templates")
def list_templates():
    """Lista i template disponibili in templates/docx/ (Template_<LANG>_*.docx)."""
    return {"templates": _list_templates_on_disk()}


@router.get("/cv/docx")
async def export_cv_docx(
    template: str = Query(..., description="Nome file template es. Template_IT_Standard_Mashfrog_v1.docx"),
    current_user: dict = Depends(get_current_user),
):
    """Genera e scarica il CV dell'utente autenticato in formato Word."""
    if ".." in template or not template.startswith("Template_") or not template.endswith(".docx"):
        raise HTTPException(400, "Nome template non valido")
    template_path = TEMPLATES_DIR / template
    if not template_path.exists():
        raise HTTPException(404, f"Template '{template}' non trovato")

    email = current_user["email"]

    parts    = template.split("_")
    language = parts[1].upper() if len(parts) > 1 else "IT"

    context = _build_context(email)

    if language == "EN":
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise HTTPException(500, "OPENAI_API_KEY non configurata — impossibile tradurre")
        context = await _translate_to_english(context, api_key)

    tpl = DocxTemplate(str(template_path))
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
