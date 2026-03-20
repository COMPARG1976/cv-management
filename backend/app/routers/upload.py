"""
Router /upload — Sprint 3 (Excel backend).
POST /cv    : carica file, chiama AI service, calcola diff con STORE, restituisce risultato
POST /apply : applica le modifiche selezionate dall'utente
"""
import asyncio
import json
import os
import time
import uuid
from collections import OrderedDict
from datetime import datetime, date
from difflib import SequenceMatcher
from typing import Optional, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Request
from fastapi.responses import StreamingResponse, Response

import app.excel_store as store
from app.excel_store import settings
from app.deps import get_current_user

router = APIRouter()

# ── Thumbnail LRU cache (max 50 entries × ~50 KB PNG ≈ 2.5 MB RAM) ───────────

_THUMB_CACHE_MAX = 50
_thumb_cache: OrderedDict[str, bytes] = OrderedDict()


def _thumb_get(key: str) -> Optional[bytes]:
    if key not in _thumb_cache:
        return None
    _thumb_cache.move_to_end(key)
    return _thumb_cache[key]


def _thumb_set(key: str, val: bytes) -> None:
    if key in _thumb_cache:
        _thumb_cache.move_to_end(key)
    else:
        if len(_thumb_cache) >= _THUMB_CACHE_MAX:
            _thumb_cache.popitem(last=False)
        _thumb_cache[key] = val


ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc"}
_UPLOAD_DIR = "/app/uploads"
_MAX_LOCAL_AGE_SECONDS = 24 * 3600  # 24 ore


import re as _re


def _build_sp_filename(email: str, doc_type: str, original_filename: str) -> str:
    """Genera nome file parlante per SharePoint.

    CV:  mario.rossi_CV_CurriculumVi.pdf
    CER: mario.rossi_CER_Fondamenti.pdf

    - email_prefix  = parte prima di '@'
    - doc_type      = 'CV' | 'CER'
    - base15        = primi 15 char alfanumerici del basename originale
    """
    prefix = email.split("@")[0]
    ext    = os.path.splitext(original_filename)[1].lower()
    base   = os.path.splitext(original_filename)[0]
    base15 = _re.sub(r"[^\w\-]", "", base)[:15]
    return f"{prefix}_{doc_type}_{base15}{ext}"


def _try_delete_local(path: str) -> None:
    """Elimina silenziosamente un file locale."""
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


def _cleanup_old_uploads() -> None:
    """Elimina i file in /app/uploads più vecchi di 24 ore (chiamata non bloccante)."""
    try:
        now = time.time()
        for fname in os.listdir(_UPLOAD_DIR):
            fpath = os.path.join(_UPLOAD_DIR, fname)
            if os.path.isfile(fpath) and (now - os.path.getmtime(fpath)) > _MAX_LOCAL_AGE_SECONDS:
                _try_delete_local(fpath)
    except OSError:
        pass


# ── String helpers ────────────────────────────────────────────────────────────

def _sim(a: str, b: str) -> float:
    """Fuzzy similarity 0–1 tra due stringhe."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _canon(v: Any) -> str:
    """Valore canonico per confronto idempotente tra DB (sempre stringa) e AI (tipizzato).

    Regole:
    - None / "None" / "null" / "" → stringa vuota
    - bool True/False → "SI"/"NO"  (come _fmt nel DB)
    - int/float interi → es. 3 → "3"  (evita "3.0" vs "3")
    - str numerica intera → normalizzata ("3.0" → "3")
    """
    if v is None:
        return ""
    if isinstance(v, bool):
        return "SI" if v else "NO"
    if isinstance(v, float):
        return str(int(v)) if v == int(v) else str(v)
    if isinstance(v, int):
        return str(v)
    s = str(v).strip()
    if s.lower() in ("none", "null", "nan", ""):
        return ""
    # Normalizza interi come stringa ("3.0" → "3")
    try:
        f = float(s)
        if f == int(f):
            return str(int(f))
    except ValueError:
        pass
    return s


def _parse_date(date_str: Optional[str]) -> Optional[date]:
    """Parsa data e normalizza SEMPRE al primo del mese (ignora il giorno)."""
    if not date_str:
        return None
    try:
        s = str(date_str).strip()
        if len(s) == 4 and s.isdigit():
            return date(int(s), 1, 1)
        if len(s) == 7 and "-" in s:
            y, m = s.split("-")
            return date(int(y), int(m), 1)
        if len(s) >= 10:
            parts = s[:10].split("-")
            return date(int(parts[0]), int(parts[1]), 1)
    except Exception:
        pass
    return None


def _date_str(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


# ── Normalizzazione AI data ───────────────────────────────────────────────────

def _normalize_category(raw: str) -> str:
    raw = (raw or "").upper()
    if raw in ("SOFT", "HARD"):
        return raw
    if any(k in raw for k in ("TECN", "TECH", "HARD", "IT")):
        return "HARD"
    return "SOFT"


def _normalize_rating(raw) -> Optional[int]:
    """Converte livello testuale o numerico in rating 1-5."""
    if raw is None:
        return None
    if isinstance(raw, int):
        return max(1, min(5, raw))
    mapping = {
        "base": 2, "beginner": 1, "basic": 2,
        "intermediate": 3, "medio": 3, "buono": 3,
        "advanced": 4, "avanzato": 4, "ottimo": 4,
        "expert": 5, "esperto": 5, "master": 5,
    }
    key = str(raw).lower().strip()
    return mapping.get(key, 3)


def _degree_level(raw: str) -> Optional[str]:
    """Normalizza un titolo di studio in degree_level."""
    raw = (raw or "").lower()
    if any(k in raw for k in ("doctor", "phd", "dottor")):
        return "DOTTORATO"
    if any(k in raw for k in ("master", "magistr", "laurea magistr", "laurea spec", "msc", "mba")):
        return "LAUREA_MAGISTRALE"
    if any(k in raw for k in ("laurea", "bachelor", "triennal", "bsc")):
        return "LAUREA_TRIENNALE"
    if any(k in raw for k in ("diploma", "maturit", "liceo", "istituto")):
        return "DIPLOMA"
    if any(k in raw for k in ("certific", "cours", "corso")):
        return "CORSO"
    return "ALTRO"


# ── Diff engine ───────────────────────────────────────────────────────────────

_PROFILE_FIELD_LABELS: dict[str, str] = {
    "title":                "Titolo professionale",
    "summary":              "Sommario",
    "phone":                "Telefono",
    "linkedin_url":         "LinkedIn",
    "birth_date":           "Data di nascita",
    "birth_place":          "Luogo di nascita",
    "residence_city":       "Città di residenza",
    "first_employment_date":"Prima occupazione",
    "availability_status":  "Disponibilità",
}
_AI_PROFILE_ALIAS: dict[str, str] = {
    "linkedin_url": "linkedin",
    "residence_city": "location",
}


def _item_field_diffs(db_item: dict, ai_item: dict, fields: list[tuple]) -> list[dict]:
    """Genera field_diffs per un item 'changed'.

    Usa _canon() per normalizzare entrambi i lati prima del confronto:
    DB archivia sempre stringhe (es. "" o "3"), AI restituisce tipi Python (None, 3, False...).
    Senza normalizzazione "" != None e 3 != "3" rompono l'idempotenza.
    """
    result = []
    for field, label in fields:
        db_v, ai_v = db_item.get(field), ai_item.get(field)
        if _canon(db_v) != _canon(ai_v):
            result.append({"field": field, "label": label,
                           "status": "changed", "db_value": db_v, "ai_value": ai_v})
    return result


def _build_section(existing: list, ai_list: list,
                   norm_fn, match_fn, diff_fields: list[tuple]) -> list[dict]:
    """Helper generico: produce la lista items di una sezione diff.
    Matching 1:1 — ogni item STORE può essere abbinato a un solo item AI e viceversa.
    Residui AI → 'new'. Residui STORE → 'db_only'.
    """
    items: list[dict] = []
    matched_ids: set = set()   # STORE item già abbinati in questa sessione

    for ai_raw in ai_list:
        ai_norm = norm_fn(ai_raw)
        if ai_norm is None:
            continue
        # Cerca il primo STORE item non ancora abbinato che supera la soglia
        match = next(
            (x for x in existing
             if x.get("id") not in matched_ids and match_fn(x, ai_norm)),
            None,
        )
        if match:
            matched_ids.add(match.get("id"))
            fds = _item_field_diffs(match, ai_norm, diff_fields)
            items.append({
                "status":      "changed" if fds else "unchanged",
                "db_id":       match.get("id"),
                "ai_data":     ai_norm,
                "field_diffs": fds,
            })
        else:
            items.append({
                "status":      "new",
                "db_id":       None,
                "ai_data":     ai_norm,
                "field_diffs": [],
            })

    # STORE item senza controparte AI
    for x in existing:
        if x.get("id") not in matched_ids:
            items.append({"status": "db_only", "db_id": x.get("id"),
                          "ai_data": None, "field_diffs": []})
    return items


def compute_diff(email: str, ai: dict) -> dict:
    """
    Confronta i dati AI con il profilo attuale in STORE.
    Restituisce struttura compatibile col frontend React:
      { profile: {field_diffs:[...]}, skills:{items:[...]}, ... }
    """
    cv_row   = store.STORE["cv_profiles"].get(email, {})
    user_row = store.STORE["users"].get(email, {})
    ai_profile = ai.get("profile", {})

    # ── Profilo scalare ────────────────────────────────────────────────────────
    field_diffs = []
    for field, label in _PROFILE_FIELD_LABELS.items():
        db_val = cv_row.get(field) or user_row.get(field)
        ai_val = (ai_profile.get(field)
                  or ai_profile.get(_AI_PROFILE_ALIAS.get(field, field)))
        if not ai_val:
            continue
        if ai_val == db_val:
            continue
        field_diffs.append({
            "field":    field,
            "label":    label,
            "status":   "new_ai" if not db_val else "changed",
            "db_value": db_val or "",
            "ai_value": ai_val,
        })

    # ── Skills ────────────────────────────────────────────────────────────────
    def _skill_norm(ai_s):
        name = (ai_s.get("skill_name") or ai_s.get("name") or "").strip()
        if not name:
            return None
        return {
            "skill_name": name,
            "category":   _normalize_category(ai_s.get("category", "HARD")),
            "rating":     _normalize_rating(ai_s.get("rating") or ai_s.get("level")),
        }

    skill_items = _build_section(
        existing   = store.STORE["skills"].get(email, []),
        ai_list    = ai.get("skills", []),
        norm_fn    = _skill_norm,
        # 0.80 (era 0.85): copre varianti come "RESTful"↔"REST", "NodeJS"↔"Node.js"
        match_fn   = lambda x, a: _sim(x.get("skill_name",""), a["skill_name"]) >= 0.80,
        diff_fields= [("category", "Categoria"), ("rating", "Livello")],
    )

    # ── Esperienze ────────────────────────────────────────────────────────────
    def _exp_norm(ai_e):
        company = (ai_e.get("company_name") or ai_e.get("company") or "").strip()
        if not company:
            return None
        return {
            "company_name":       company,
            "client_name":        ai_e.get("client_name"),
            "role":               (ai_e.get("role") or "").strip(),
            "start_date":         _date_str(_parse_date(ai_e.get("start_date"))),
            "end_date":           _date_str(_parse_date(ai_e.get("end_date"))),
            "is_current":         ai_e.get("is_current", False),
            "project_description":ai_e.get("project_description") or ai_e.get("description"),
            "activities":         ai_e.get("activities"),
        }

    exp_items = _build_section(
        existing   = store.STORE["experiences"].get(email, []),
        ai_list    = ai.get("references", ai.get("experiences", [])),
        norm_fn    = _exp_norm,
        match_fn   = lambda x, a: (
            _sim(x.get("company_name",""), a["company_name"]) >= 0.80
            and _sim(x.get("role",""), a["role"]) >= 0.70
        ),
        diff_fields= [
            ("company_name","Azienda"), ("role","Ruolo"),
            ("start_date","Inizio"),    ("end_date","Fine"),
            ("project_description","Descrizione"), ("activities","Attività"),
        ],
    )

    # ── Education ─────────────────────────────────────────────────────────────
    def _edu_norm(ai_ed):
        inst = (ai_ed.get("institution") or "").strip()
        if not inst:
            return None
        return {
            "institution":    inst,
            "degree_level":   _degree_level(ai_ed.get("degree_level") or ai_ed.get("degree_type") or ""),
            "field_of_study": ai_ed.get("field_of_study"),
            "graduation_year":ai_ed.get("graduation_year"),
            "grade":          ai_ed.get("grade"),
        }

    edu_items = _build_section(
        existing   = store.STORE["educations"].get(email, []),
        ai_list    = ai.get("educations", []),
        norm_fn    = _edu_norm,
        match_fn   = lambda x, a: _sim(x.get("institution",""), a["institution"]) >= 0.80,
        diff_fields= [("degree_level","Titolo"), ("field_of_study","Materia"), ("graduation_year","Anno")],
    )

    # ── Certifications ────────────────────────────────────────────────────────
    def _cert_norm(ai_c):
        name = (ai_c.get("name") or "").strip()
        if not name:
            return None
        year = ai_c.get("year")
        if not year and ai_c.get("issue_date"):
            s = str(ai_c["issue_date"])[:4]
            year = int(s) if s.isdigit() else None
        return {
            "name":        name,
            "issuing_org": ai_c.get("issuing_org"),
            "cert_code":   ai_c.get("cert_code"),
            "year":        year,
        }

    cert_items = _build_section(
        existing   = store.STORE["certifications"].get(email, []),
        ai_list    = ai.get("certifications", []),
        norm_fn    = _cert_norm,
        match_fn   = lambda x, a: _sim(x.get("name",""), a["name"]) >= 0.80,
        diff_fields= [("issuing_org","Ente"), ("year","Anno"), ("cert_code","Codice")],
    )

    # ── Languages ─────────────────────────────────────────────────────────────
    def _lang_norm(ai_l):
        name = (ai_l.get("language_name") or ai_l.get("language") or "").strip()
        if not name:
            return None
        return {"language_name": name, "level": ai_l.get("level")}

    lang_items = _build_section(
        existing   = store.STORE["languages"].get(email, []),
        ai_list    = ai.get("languages", []),
        norm_fn    = _lang_norm,
        match_fn   = lambda x, a: _sim(x.get("language_name",""), a["language_name"]) >= 0.85,
        diff_fields= [("level","Livello")],
    )

    return {
        "profile":        {"field_diffs": field_diffs},
        "skills":         {"items": skill_items},
        "references":     {"items": exp_items},
        "educations":     {"items": edu_items},
        "certifications": {"items": cert_items},
        "languages":      {"items": lang_items},
    }


# ── Endpoint: upload CV ───────────────────────────────────────────────────────

@router.post("/cv")
async def upload_cv(
    file: UploadFile = File(...),
    ai_update: str  = Form(default="false"),    # "true" | "false"
    tags_json: str  = Form(default="[]"),        # JSON array of strings
    current_user: dict = Depends(get_current_user),
):
    """
    Carica un CV (PDF/DOCX).
    Se ai_update=true chiama il servizio AI e restituisce un diff da revisionare.
    Se ai_update=false salva solo il file (nessuna analisi AI).
    """
    use_ai = ai_update.lower() in ("true", "1", "yes")

    try:
        tags_list = json.loads(tags_json) if tags_json else []
        if not isinstance(tags_list, list):
            tags_list = []
    except Exception:
        tags_list = []

    _cleanup_old_uploads()  # pulizia non bloccante dei file locali scaduti

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Tipo file non supportato: {ext}")

    content = await file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(413, f"File troppo grande (max {settings.max_upload_size_mb} MB)")

    # ── Salva file su disco (volume condiviso con ai-services) ─────────────────
    upload_dir = "/app/uploads"
    os.makedirs(upload_dir, exist_ok=True)
    safe_name = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(upload_dir, safe_name)
    with open(file_path, "wb") as f:
        f.write(content)

    # ── Prepara coordinate SharePoint ─────────────────────────────────────────
    # Struttura tipo-first flat: CV/<nome_parlante>.pdf
    # Il file locale usa uuid (temporaneo); su SP va il nome leggibile.
    email   = current_user["email"]
    sp_name = _build_sp_filename(email, "CV", file.filename or safe_name)
    sp_path = f"CV/{sp_name}"

    # ── Se AI disabilitato: upload SP sequenziale e ritorna ───────────────────
    if not use_ai:
        sp_url = ""
        try:
            sp_url = await store._sp_upload(sp_path, content) or ""
        except Exception as e:
            print(f"[Upload] SP upload fallito: {e}")
        if not sp_url and store.settings.sharepoint_enabled:
            _try_delete_local(file_path)
            raise HTTPException(502, "Upload su SharePoint fallito. "
                                     "Riprovare quando il file non è aperto in Excel.")
        doc = await store.add_document(email, {
            "original_filename": file.filename,
            "doc_type":          "UPLOAD",
            "upload_date":       datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ai_updated":        False,
            "sharepoint_path":   sp_path,
            "sharepoint_url":    sp_url,
            "tags":              tags_list,
        })
        _try_delete_local(file_path)
        return {"document_id": doc["id"], "filename": file.filename, "ai_skipped": True}

    # ── AI abilitato: upload SP e parse AI in PARALLELO ───────────────────────
    # L'AI parse usa solo il path locale (già su disco), non dipende dall'URL SP.
    # I due task corrono contemporaneamente: si risparmia l'intera durata dell'upload SP
    # (tipicamente 3-8s) che prima bloccava l'inizio del parse.
    ai_url_base = settings.ai_service_url.rstrip("/")

    async def _do_sp_upload() -> str:
        try:
            return await store._sp_upload(sp_path, content) or ""
        except Exception as e:
            print(f"[Upload] SP upload fallito: {e}")
            return ""

    async def _do_ai_parse() -> httpx.Response:
        async with httpx.AsyncClient(timeout=120) as client:
            return await client.post(
                f"{ai_url_base}/parse",
                json={"file_path": file_path, "document_id": ""},
            )

    try:
        sp_url, ai_http_resp = await asyncio.gather(_do_sp_upload(), _do_ai_parse())
    except httpx.RequestError as e:
        _try_delete_local(file_path)
        raise HTTPException(502, f"AI service non raggiungibile: {e}")
    finally:
        # File locale eliminato dopo che AI ha letto il file (sia successo che errore)
        _try_delete_local(file_path)

    # ── Controlla esito upload SP ──────────────────────────────────────────────
    if not sp_url and store.settings.sharepoint_enabled:
        raise HTTPException(502, "Upload su SharePoint fallito: il file non è stato salvato. "
                                 "Riprovare quando il file non è aperto in Excel.")

    # ── Controlla risposta AI ──────────────────────────────────────────────────
    if ai_http_resp.status_code != 200:
        raise HTTPException(502, f"AI service errore {ai_http_resp.status_code}: {ai_http_resp.text[:200]}")
    ai_resp = ai_http_resp.json()
    if ai_resp.get("status") == "error":
        raise HTTPException(502, f"AI parsing fallito: {ai_resp.get('error', 'errore sconosciuto')}")

    # ── Crea record Document (ora abbiamo sia sp_url che ai ok) ───────────────
    doc = await store.add_document(email, {
        "original_filename": file.filename,
        "doc_type":          "UPLOAD",
        "upload_date":       datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ai_updated":        False,
        "sharepoint_path":   sp_path,
        "sharepoint_url":    sp_url,
        "tags":              tags_list,
    })

    # ── Calcola diff e restituisci ─────────────────────────────────────────────
    diff = compute_diff(email, ai_resp.get("data") or {})
    diff["document_id"] = doc["id"]
    return diff


# ── Endpoint: apply diff ──────────────────────────────────────────────────────

@router.post("/apply")
async def apply_diff(
    payload: dict,
    current_user: dict = Depends(get_current_user),
):
    """
    Applica le selezioni dell'utente al profilo STORE.
    payload (da buildApplyRequest frontend):
      { document_id,
        profile_updates: {field: value, ...},
        skills:         {add:[...], update:[{db_id,...}]},
        references:     {add:[...], update:[{db_id,...}]},
        educations:     {add:[...], update:[{db_id,...}]},
        certifications: {add:[...], update:[{db_id,...}]},
        languages:      {add:[...], update:[{db_id,...}]} }
    """
    email = current_user["email"]
    changes = {"profile": 0, "skills": 0, "references": 0,
               "educations": 0, "certifications": 0, "languages": 0}

    # ── Profilo scalare ────────────────────────────────────────────────────────
    profile_updates = payload.get("profile_updates") or {}
    if profile_updates:
        await store.update_cv_profile(email, profile_updates)
        changes["profile"] = len(profile_updates)

    # ── Helper generico per sezioni ───────────────────────────────────────────
    async def _apply_section(key: str, add_fn, update_fn, dup_fn):
        sec = payload.get(key) or {}
        for item in sec.get("add", []):
            if item and not dup_fn(item):
                await add_fn(email, item)
                changes[key] += 1
        for item in sec.get("update", []):
            db_id = item.pop("db_id", None) if item else None
            if db_id and item:
                await update_fn(email, db_id, item)
                changes[key] += 1

    # Snapshot pre-apply: la dedup controlla solo ciò che esisteva PRIMA
    # di questa operazione, non gli item appena aggiunti nella stessa chiamata.
    _snap_skills  = list(store.STORE["skills"].get(email, []))
    _snap_exp     = list(store.STORE["experiences"].get(email, []))
    _snap_edu     = list(store.STORE["educations"].get(email, []))
    _snap_certs   = list(store.STORE["certifications"].get(email, []))
    _snap_langs   = list(store.STORE["languages"].get(email, []))

    # ── Skills ────────────────────────────────────────────────────────────────
    await _apply_section(
        "skills",
        add_fn    = store.add_skill,
        update_fn = store.update_skill,
        dup_fn    = lambda a: any(
            _sim(s.get("skill_name",""), a.get("skill_name","")) >= 0.85
            for s in _snap_skills
        ),
    )

    # ── Esperienze ────────────────────────────────────────────────────────────
    await _apply_section(
        "references",
        add_fn    = store.add_experience,
        update_fn = store.update_experience,
        dup_fn    = lambda a: any(
            _sim(e.get("company_name",""), a.get("company_name","")) >= 0.80
            and _sim(e.get("role",""), a.get("role","")) >= 0.70
            for e in _snap_exp
        ),
    )

    # ── Education ─────────────────────────────────────────────────────────────
    await _apply_section(
        "educations",
        add_fn    = store.add_education,
        update_fn = store.update_education,
        dup_fn    = lambda a: any(
            _sim(e.get("institution",""), a.get("institution","")) >= 0.80
            for e in _snap_edu
        ),
    )

    # ── Certifications ────────────────────────────────────────────────────────
    await _apply_section(
        "certifications",
        add_fn    = store.add_certification,
        update_fn = store.update_certification,
        dup_fn    = lambda a: any(
            _sim(c.get("name",""), a.get("name","")) >= 0.80
            for c in _snap_certs
        ),
    )

    # ── Languages ─────────────────────────────────────────────────────────────
    await _apply_section(
        "languages",
        add_fn    = store.add_language,
        update_fn = store.update_language,
        dup_fn    = lambda a: any(
            _sim(l.get("language_name",""), a.get("language_name","")) >= 0.85
            for l in _snap_langs
        ),
    )

    # ── Marca documento come AI-aggiornato ────────────────────────────────────
    doc_id = payload.get("document_id")
    if doc_id:
        await store.update_document(email, doc_id, {"ai_updated": True})

    return {
        "applied_count": sum(changes.values()),
        "sections":       changes,
    }


# ── Endpoint: lista documenti utente ──────────────────────────────────────────

@router.get("/documents")
async def list_documents(current_user: dict = Depends(get_current_user)):
    email = current_user["email"]
    docs = store.STORE["documents"].get(email, [])
    return docs


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    current_user: dict = Depends(get_current_user),
):
    email = current_user["email"]
    ok = await store.delete_document(email, doc_id)
    if not ok:
        raise HTTPException(404, "Documento non trovato")
    return {"status": "deleted"}


@router.get("/documents/{doc_id}/download")
async def download_document(
    doc_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Scarica un CV archiviato: prima da SharePoint, poi dal volume locale."""
    email = current_user["email"]
    docs  = store.STORE["documents"].get(email, [])
    doc   = next((d for d in docs if d["id"] == doc_id), None)
    if not doc:
        raise HTTPException(404, "Documento non trovato")

    filename = doc.get("original_filename", "cv_document")
    sp_path  = doc.get("sharepoint_path", "")
    upload_dir = "/app/uploads"

    # Prova SharePoint prima
    if sp_path and store.settings.sharepoint_enabled:
        try:
            content = await store._sp_download(sp_path)
            if content:
                import mimetypes
                mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
                return StreamingResponse(
                    iter([content]),
                    media_type=mime,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'},
                )
        except Exception as e:
            print(f"[Download] SP download fallito, provo locale: {e}")

    # Fallback: cerca nella cartella locale per nome originale o safe_name
    # Cerca per sharepoint_path che contiene il safe_name
    safe_name = sp_path.rsplit("/", 1)[-1] if sp_path else ""
    local_path = os.path.join(upload_dir, safe_name) if safe_name else None

    if local_path and os.path.isfile(local_path):
        import mimetypes
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        with open(local_path, "rb") as f:
            content = f.read()
        return StreamingResponse(
            iter([content]),
            media_type=mime,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    raise HTTPException(404, "File non trovato su SharePoint né in locale")


# ── Thumbnail endpoint ─────────────────────────────────────────────────────────

@router.get("/documents/cert/{cert_id}/thumbnail")
async def cert_thumbnail(
    cert_id: str,
    request: Request,
    token: Optional[str] = Query(default=None, include_in_schema=False),
):
    """
    Genera una miniatura PNG (prima pagina PDF) per una certificazione.
    Usa LRU cache in-memory (max 50 entry).
    Autenticazione via Bearer header o query param ?token=.
    """
    from app.security import decode_token

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        jwt = auth_header[7:]
    elif token:
        jwt = token
    else:
        raise HTTPException(401, "Non autenticato")

    try:
        claims = decode_token(jwt)
    except Exception:
        raise HTTPException(401, "Token non valido")

    email = claims.get("sub")
    if not email or not store.get_user(email):
        raise HTTPException(401, "Utente non trovato")

    # Controlla cache
    cached = _thumb_get(cert_id)
    if cached is not None:
        return Response(content=cached, media_type="image/png")

    # Trova la cert
    cert = next((c for c in store.get_certifications(email) if c["id"] == cert_id), None)
    if not cert:
        raise HTTPException(404, "Certificazione non trovata")

    fp = cert.get("uploaded_file_path", "")
    if not fp:
        raise HTTPException(404, "Nessun file allegato")

    # Leggi il contenuto del file
    try:
        if fp.startswith("sp:"):
            content_bytes = await store._sp_download(fp[3:])
            if not content_bytes:
                raise HTTPException(404, "File non trovato su SharePoint")
        else:
            p = os.path.join("/app", fp.lstrip("/"))
            if not os.path.isfile(p):
                raise HTTPException(404, "File non trovato")
            with open(p, "rb") as fh:
                content_bytes = fh.read()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(404, f"Errore lettura file: {e}")

    # Genera thumbnail con PyMuPDF
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=content_bytes, filetype="pdf")
        page = doc[0]
        mat = fitz.Matrix(0.4, 0.4)  # scala 0.4 → ~240px larghezza per A4
        pix = page.get_pixmap(matrix=mat)
        png_bytes = pix.tobytes("png")
        doc.close()
    except Exception:
        raise HTTPException(404, "Impossibile generare thumbnail (file non PDF o errore)")

    _thumb_set(cert_id, png_bytes)
    return Response(content=png_bytes, media_type="image/png")


@router.delete("/documents/cert/{cert_id}/thumbnail-cache", status_code=204)
async def invalidate_cert_thumbnail_cache(
    cert_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Invalida la cache thumbnail per una cert specifica (chiamare dopo upload nuovo doc)."""
    if cert_id in _thumb_cache:
        del _thumb_cache[cert_id]
