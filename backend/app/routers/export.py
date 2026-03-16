"""
Router /export — Sprint 5.
GET /export/templates       → lista template disponibili in templates/docx/
GET /export/cv/docx         → genera e scarica il CV come Word
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
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_user
from app.models import CV, User

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
        display = " ".join(parts[2:])  # Standard Mashfrog v1
        result.append({
            "filename":     f.name,
            "language":     lang,
            "display_name": display,
            "label":        f"[{lang}] {display}",
        })
    return result


def _sort_refs(refs: list) -> list:
    """end_date DESC NULLS FIRST → start_date DESC  (identico alla UI)."""
    def key(r):
        end   = r.end_date.isoformat()[:7]   if r.end_date   else "9999-99"
        start = r.start_date.isoformat()[:7] if r.start_date else ""
        return (end, start)
    return sorted(refs, key=key, reverse=True)


def _fmt_date(d) -> Optional[str]:
    """date → 'MM/YYYY' oppure None."""
    if d is None:
        return None
    try:
        return d.strftime("%m/%Y")
    except Exception:
        return str(d)


def _rating_stars(rating: Optional[int]) -> str:
    """1-5 → stringa ★★★★☆."""
    if not rating:
        return ""
    r = max(0, min(5, int(rating)))
    return "★" * r + "☆" * (5 - r)


def _build_context(cv: CV, user: User) -> dict:
    """
    Costruisce il contesto Jinja2 con tutti i campi e alias per compatibilità
    tra Template_IT_Standard, Template_EN_Standard e Template_IT_Esempio.
    """
    # ── Esperienze ────────────────────────────────────────────────────────────
    sorted_refs = _sort_refs(cv.references or [])
    experiences = []
    for ref in sorted_refs:
        start_fmt = _fmt_date(ref.start_date) or ""
        end_fmt   = _fmt_date(ref.end_date)
        experiences.append({
            # nomi usati nei template Standard v1
            "company":              ref.company_name or "",
            "start_date":           start_fmt,
            "end_date_fmt":         end_fmt,
            # alias aggiuntivi per compatibilità altri template
            "company_name":         ref.company_name or "",
            "client_name":          ref.client_name  or "",
            "role":                 ref.role          or "",
            "start_date_fmt":       start_fmt,
            "project_description":  ref.project_description or "",
            "activities":           ref.activities    or "",
            "skills_csv":           ", ".join(ref.skills_acquired or []),
            "skills_acquired":      ref.skills_acquired or [],
        })

    # ── Competenze ────────────────────────────────────────────────────────────
    skills_hard, skills_soft = [], []
    for sk in sorted(cv.skills or [], key=lambda x: x.skill_name):
        entry = {
            "skill_name":   sk.skill_name,
            "name":         sk.skill_name,       # alias Template_IT_Esempio
            "category":     sk.category.value if sk.category else "",
            "rating":       sk.rating or 0,
            "rating_stars": _rating_stars(sk.rating),
        }
        if sk.category and sk.category.value == "HARD":
            skills_hard.append(entry)
        else:
            skills_soft.append(entry)

    # ── Formazione ────────────────────────────────────────────────────────────
    educations = [
        {
            "institution":    edu.institution,
            "degree_level":   edu.degree_level.value if edu.degree_level else "",
            "degree_type":    edu.degree_level.value if edu.degree_level else "",  # alias
            "field_of_study": edu.field_of_study or "",
            "graduation_year": edu.graduation_year or "",
            "end_year":        edu.graduation_year or "",   # alias
            "start_year":      "",
            "grade":           edu.grade  or "",
            "notes":           edu.notes  or "",
        }
        for edu in sorted(cv.educations or [], key=lambda e: e.graduation_year or 9999)
    ]

    # ── Lingue ────────────────────────────────────────────────────────────────
    languages = [
        {
            "language_name": lang.language_name,
            "language":      lang.language_name,   # alias Template_IT_Esempio
            "level":         lang.level.value if lang.level else "",
            "notes":         "",
        }
        for lang in (cv.languages or [])
    ]

    # ── Certificazioni ────────────────────────────────────────────────────────
    certifications = [
        {
            "name":        cert.name,
            "cert_code":   cert.cert_code   or "",
            "issuing_org": cert.issuing_org or "",
            "year":        cert.year        or "",
            "issue_date":  cert.year        or "",   # alias Template_IT_Esempio
            "expiry_date": _fmt_date(cert.expiry_date) or "",
            "version":     cert.version     or "",
            "doc_url":     cert.doc_url     or "",
        }
        for cert in sorted(cv.certifications or [], key=lambda x: -(x.year or 0))
    ]

    return {
        # Anagrafica
        "full_name":          user.full_name          or "",
        "email":              user.email              or "",
        "job_title":          cv.title                or "",
        "phone":              cv.phone                or "",
        "linkedin_url":       cv.linkedin_url         or "",
        "location":           cv.residence_city       or "",
        "residence_city":     cv.residence_city       or "",
        "birth_date":         _fmt_date(cv.birth_date) or "",
        "summary":            cv.summary              or "",
        "hire_date_mashfrog": _fmt_date(user.hire_date_mashfrog) or "",
        "mashfrog_office":    user.mashfrog_office     or "",
        "bu_mashfrog":        user.bu_mashfrog         or "",
        # Sezioni
        "experiences":        experiences,
        "skills_hard":        skills_hard,
        "skills_soft":        skills_soft,
        "skills":             skills_hard + skills_soft,   # alias Template_IT_Esempio
        "educations":         educations,
        "languages":          languages,
        "certifications":     certifications,
    }


async def _translate_to_english(context: dict, api_key: str) -> dict:
    """
    Traduce in inglese i campi testuali tramite OpenAI gpt-4o-mini.
    Tutte le chiamate vengono raggruppate in un unico request batch.
    """
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Genera e scarica il CV dell'utente autenticato in formato Word."""

    # Sicurezza: path traversal + solo file dalla dir autorizzata
    if ".." in template or not template.startswith("Template_") or not template.endswith(".docx"):
        raise HTTPException(400, "Nome template non valido")
    template_path = TEMPLATES_DIR / template
    if not template_path.exists():
        raise HTTPException(404, f"Template '{template}' non trovato")

    # Carica CV con tutte le relazioni
    cv = (
        db.query(CV)
        .options(
            selectinload(CV.skills),
            selectinload(CV.educations),
            selectinload(CV.languages),
            selectinload(CV.references),
            selectinload(CV.certifications),
        )
        .filter(CV.user_id == current_user.id)
        .first()
    )
    if not cv:
        raise HTTPException(404, "CV non trovato per l'utente corrente")

    # Lingua dal nome file: Template_IT_… → "IT", Template_EN_… → "EN"
    parts   = template.split("_")
    language = parts[1].upper() if len(parts) > 1 else "IT"

    # Costruisce contesto
    context = _build_context(cv, current_user)

    # Traduce se template EN
    if language == "EN":
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise HTTPException(500, "OPENAI_API_KEY non configurata — impossibile tradurre")
        context = await _translate_to_english(context, api_key)

    # Render docxtpl
    tpl = DocxTemplate(str(template_path))
    tpl.render(context)

    output = io.BytesIO()
    tpl.save(output)
    output.seek(0)

    # Nome file output: CV_NomeCognome_Standard_Mashfrog_v1.docx
    user_slug  = (current_user.full_name or "cv").replace(" ", "_")
    tmpl_slug  = template.replace(".docx", "").replace("Template_IT_", "").replace("Template_EN_", "")
    filename   = f"CV_{user_slug}_{tmpl_slug}.docx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
