"""
Router /cv — profilo CV completo + CRUD sub-risorse + suggest.
"""
import os
import re
from typing import List, Dict, Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, status
from fastapi.responses import RedirectResponse

import app.excel_store as store
from app.excel_store import settings
from app.deps import get_current_user
from app.schemas import (
    CVFullResponse, CVUpdate,
    CVSkillCreate, CVSkillResponse,
    EducationCreate, EducationResponse,
    LanguageCreate, LanguageResponse,
    ReferenceCreate, ReferenceResponse,
    CertificationCreate, CertificationResponse,
    SkillSuggestion, CertSuggestion,
    CVDocumentResponse,
)

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _404(detail: str):
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _parse_bool(v) -> bool:
    return str(v).upper() in ("SI", "TRUE", "1", "YES")


def _parse_int(v) -> Optional[int]:
    try:
        return int(v) if v not in (None, "") else None
    except (ValueError, TypeError):
        return None


def _parse_date_str(v) -> Optional[str]:
    if not v or str(v).strip() in ("", "None"):
        return None
    s = str(v).strip()
    # Anno-solo (es. "2026" da Excel) → "2026-01-01" per soddisfare Pydantic date
    if re.match(r'^\d{4}$', s):
        return f"{s}-01-01"
    return s


def _row_to_skill(r: dict) -> CVSkillResponse:
    return CVSkillResponse(
        id=r["id"],
        skill_name=r.get("skill_name", ""),
        category=r.get("category", "HARD"),
        rating=_parse_int(r.get("rating")),
        notes=r.get("notes") or None,
    )


def _row_to_education(r: dict) -> EducationResponse:
    return EducationResponse(
        id=r["id"],
        institution=r.get("institution", ""),
        degree_level=r.get("degree_level") or None,
        field_of_study=r.get("field_of_study") or None,
        graduation_year=_parse_int(r.get("graduation_year")),
        graduation_date=None,
        grade=r.get("grade") or None,
        notes=r.get("notes") or None,
    )


def _row_to_language(r: dict) -> LanguageResponse:
    return LanguageResponse(
        id=r["id"],
        language_name=r.get("language_name", ""),
        level=r.get("level") or None,
    )


def _row_to_reference(r: dict) -> ReferenceResponse:
    return ReferenceResponse(
        id=r["id"],
        company_name=r.get("company_name") or None,
        client_name=r.get("client_name") or None,
        role=r.get("role") or None,
        start_date=_parse_date_str(r.get("start_date")),
        end_date=_parse_date_str(r.get("end_date")),
        is_current=_parse_bool(r.get("is_current", "NO")),
        project_description=r.get("project_description") or None,
        activities=r.get("activities") or None,
        sort_order=_parse_int(r.get("sort_order")) or 0,
    )


def _row_to_cert(r: dict) -> CertificationResponse:
    tags_raw = r.get("tags", "")
    tags = [t.strip() for t in str(tags_raw).split("|") if t.strip()] if tags_raw else []
    return CertificationResponse(
        id=r["id"],
        name=r.get("name", ""),
        issuing_org=r.get("issuing_org") or None,
        cert_code=r.get("cert_code") or None,
        version=r.get("version") or None,
        year=_parse_int(r.get("year")),
        expiry_date=_parse_date_str(r.get("expiry_date")),
        has_formal_cert=_parse_bool(r.get("has_formal_cert", "SI")),
        doc_attachment_type=r.get("doc_attachment_type") or "NONE",
        doc_url=r.get("doc_url") or None,
        credly_badge_id=r.get("credly_badge_id") or None,
        uploaded_file_path=r.get("uploaded_file_path") or None,
        tags=tags or None,
        notes=r.get("notes") or None,
    )


def _row_to_document(r: dict) -> CVDocumentResponse:
    tags_raw = r.get("tags", "")
    tags = [t.strip() for t in str(tags_raw).split("|") if t.strip()] if tags_raw else []
    return CVDocumentResponse(
        id=r["id"],
        original_filename=r.get("original_filename", ""),
        doc_type=r.get("doc_type", "UPLOAD"),
        sharepoint_path=r.get("sharepoint_path") or None,
        sharepoint_url=r.get("sharepoint_url") or None,
        upload_date=r.get("upload_date") or None,
        ai_updated=_parse_bool(r.get("ai_updated", "NO")),
        tags=tags or None,
    )


def _build_full_response(email: str) -> CVFullResponse:
    user    = store.get_user(email) or {}
    profile = store.get_cv_profile(email) or {}
    score   = store.compute_completeness(email)
    return CVFullResponse(
        email=email,
        title=profile.get("title") or None,
        summary=profile.get("summary") or None,
        phone=profile.get("phone") or None,
        linkedin_url=profile.get("linkedin_url") or None,
        birth_date=_parse_date_str(profile.get("birth_date")),
        birth_place=profile.get("birth_place") or None,
        residence_city=profile.get("residence_city") or None,
        first_employment_date=_parse_date_str(profile.get("first_employment_date")),
        availability_status=profile.get("availability_status") or "IN_STAFF",
        completeness_score=score,
        updated_at=profile.get("updated_at") or None,
        full_name=user.get("full_name") or None,
        hire_date_mashfrog=_parse_date_str(user.get("hire_date")),
        mashfrog_office=user.get("mashfrog_office") or None,
        bu_mashfrog=user.get("bu_mashfrog") or None,
        educations=[_row_to_education(r) for r in store.get_educations(email)],
        languages=[_row_to_language(r) for r in store.get_languages(email)],
        skills=[_row_to_skill(r) for r in store.get_skills(email)],
        references=[_row_to_reference(r) for r in store.get_experiences(email)],
        certifications=[_row_to_cert(r) for r in store.get_certifications(email)],
        documents=[_row_to_document(r) for r in store.get_documents(email)],
    )


# ── Suggest ───────────────────────────────────────────────────────────────────

@router.get("/skills/suggest", response_model=List[SkillSuggestion])
def suggest_skills(
    q: str = Query(default=""),
    limit: int = Query(default=20, le=50),
    _: dict = Depends(get_current_user),
):
    from collections import Counter
    q_lower = q.lower().strip()
    seen: Counter = Counter()
    for items in store.STORE["skills"].values():
        for s in items:
            name = s.get("skill_name", "")
            cat  = s.get("category", "HARD")
            if q_lower in name.lower():
                seen[(name, cat)] += 1
    return [SkillSuggestion(skill_name=k[0], category=k[1], count=v)
            for k, v in seen.most_common(limit)]


@router.get("/certifications/suggest", response_model=List[CertSuggestion])
def suggest_certifications(
    q: str = Query(default=""),
    limit: int = Query(default=20, le=50),
    _: dict = Depends(get_current_user),
):
    from collections import Counter
    q_lower = q.lower().strip()
    seen: Counter = Counter()
    for items in store.STORE["certifications"].values():
        for c in items:
            code = c.get("cert_code", "")
            name = c.get("name", "")
            if not code:
                continue
            if q_lower in code.lower() or q_lower in name.lower():
                seen[(code, name, c.get("issuing_org",""), c.get("version",""))] += 1
    return [CertSuggestion(cert_code=k[0], name=k[1], issuing_org=k[2] or None,
                           version=k[3] or None, count=v)
            for k, v in seen.most_common(limit)]


# ── GET / PUT /cv/me ──────────────────────────────────────────────────────────

@router.get("/me", response_model=CVFullResponse)
def get_my_cv(current_user: dict = Depends(get_current_user)):
    return _build_full_response(current_user["email"])


@router.put("/me", response_model=CVFullResponse)
async def update_my_cv(data: CVUpdate, current_user: dict = Depends(get_current_user)):
    email = current_user["email"]
    dump  = data.model_dump(exclude_none=True)
    user_fields = {"hire_date_mashfrog", "mashfrog_office", "bu_mashfrog"}
    profile_upd = {k: str(v) if v is not None else "" for k, v in dump.items() if k not in user_fields}
    user_upd    = {k: str(v) if v is not None else "" for k, v in dump.items() if k in user_fields}
    if profile_upd:
        await store.update_cv_profile(email, profile_upd)
    if user_upd:
        if "hire_date_mashfrog" in user_upd:
            user_upd["hire_date"] = user_upd.pop("hire_date_mashfrog")
        await store.update_user(email, user_upd)
    return _build_full_response(email)


# ── Skills ────────────────────────────────────────────────────────────────────

@router.post("/me/skills", response_model=CVSkillResponse, status_code=201)
async def add_skill(data: CVSkillCreate, current_user: dict = Depends(get_current_user)):
    return _row_to_skill(await store.add_skill(current_user["email"], data.model_dump()))


@router.put("/me/skills/{skill_id}", response_model=CVSkillResponse)
async def update_skill(skill_id: str, data: CVSkillCreate, current_user: dict = Depends(get_current_user)):
    try:
        return _row_to_skill(await store.update_skill(current_user["email"], skill_id, data.model_dump(exclude_none=True)))
    except KeyError:
        _404("Skill non trovata")


@router.delete("/me/skills/{skill_id}", status_code=204)
async def delete_skill(skill_id: str, current_user: dict = Depends(get_current_user)):
    await store.delete_skill(current_user["email"], skill_id)


# ── Educations ────────────────────────────────────────────────────────────────

@router.post("/me/educations", response_model=EducationResponse, status_code=201)
async def add_education(data: EducationCreate, current_user: dict = Depends(get_current_user)):
    return _row_to_education(await store.add_education(current_user["email"], data.model_dump()))


@router.put("/me/educations/{edu_id}", response_model=EducationResponse)
async def update_education(edu_id: str, data: EducationCreate, current_user: dict = Depends(get_current_user)):
    try:
        return _row_to_education(await store.update_education(current_user["email"], edu_id, data.model_dump(exclude_none=True)))
    except KeyError:
        _404("Formazione non trovata")


@router.delete("/me/educations/{edu_id}", status_code=204)
async def delete_education(edu_id: str, current_user: dict = Depends(get_current_user)):
    await store.delete_education(current_user["email"], edu_id)


# ── Languages ─────────────────────────────────────────────────────────────────

@router.post("/me/languages", response_model=LanguageResponse, status_code=201)
async def add_language(data: LanguageCreate, current_user: dict = Depends(get_current_user)):
    return _row_to_language(await store.add_language(current_user["email"], data.model_dump()))


@router.put("/me/languages/{lang_id}", response_model=LanguageResponse)
async def update_language(lang_id: str, data: LanguageCreate, current_user: dict = Depends(get_current_user)):
    try:
        return _row_to_language(await store.update_language(current_user["email"], lang_id, data.model_dump(exclude_none=True)))
    except KeyError:
        _404("Lingua non trovata")


@router.delete("/me/languages/{lang_id}", status_code=204)
async def delete_language(lang_id: str, current_user: dict = Depends(get_current_user)):
    await store.delete_language(current_user["email"], lang_id)


# ── References ────────────────────────────────────────────────────────────────

@router.post("/me/references", response_model=ReferenceResponse, status_code=201)
async def add_reference(data: ReferenceCreate, current_user: dict = Depends(get_current_user)):
    return _row_to_reference(await store.add_experience(current_user["email"], data.model_dump()))


@router.put("/me/references/{ref_id}", response_model=ReferenceResponse)
async def update_reference(ref_id: str, data: ReferenceCreate, current_user: dict = Depends(get_current_user)):
    try:
        return _row_to_reference(await store.update_experience(current_user["email"], ref_id, data.model_dump(exclude_none=True)))
    except KeyError:
        _404("Esperienza non trovata")


@router.delete("/me/references/{ref_id}", status_code=204)
async def delete_reference(ref_id: str, current_user: dict = Depends(get_current_user)):
    await store.delete_experience(current_user["email"], ref_id)


# ── Certifications ────────────────────────────────────────────────────────────

@router.post("/me/certifications", response_model=CertificationResponse, status_code=201)
async def add_certification(data: CertificationCreate, current_user: dict = Depends(get_current_user)):
    return _row_to_cert(await store.add_certification(current_user["email"], data.model_dump()))


@router.put("/me/certifications/{cert_id}", response_model=CertificationResponse)
async def update_certification(cert_id: str, data: CertificationCreate, current_user: dict = Depends(get_current_user)):
    try:
        return _row_to_cert(await store.update_certification(current_user["email"], cert_id, data.model_dump(exclude_none=True)))
    except KeyError:
        _404("Certificazione non trovata")


@router.delete("/me/certifications/{cert_id}", status_code=204)
async def delete_certification(cert_id: str, current_user: dict = Depends(get_current_user)):
    await store.delete_certification(current_user["email"], cert_id)


@router.post("/me/certifications/{cert_id}/upload-doc", response_model=CertificationResponse)
async def upload_cert_doc(cert_id: str, file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    email = current_user["email"]
    certs = store.get_certifications(email)
    cert  = next((c for c in certs if c["id"] == cert_id), None)
    if not cert:
        _404("Certificazione non trovata")
    content_bytes = await file.read()
    if len(content_bytes) > 10 * 1024 * 1024:
        raise HTTPException(400, "File troppo grande (max 10 MB)")
    ext = os.path.splitext(file.filename or "doc")[1].lower() or ".bin"
    if ext not in {".pdf", ".jpg", ".jpeg", ".png", ".docx", ".doc"}:
        raise HTTPException(400, f"Formato non supportato ({ext})")
    if settings.sharepoint_enabled:
        from app.sharepoint import upload_cert_file
        sp_path = await upload_cert_file(
            user_email=email, cert_id=cert_id,
            original_filename=file.filename or f"cert_{cert_id}{ext}",
            content=content_bytes,
            user_full_name=current_user.get("full_name", ""),
            cert_name=cert.get("name", ""),
        )
        r = await store.update_certification(email, cert_id,
            {"uploaded_file_path": f"sp:{sp_path}", "doc_attachment_type": "SHAREPOINT"})
    else:
        safe = f"cert_{cert_id}{ext}"
        d = os.path.join(settings.upload_dir, "certs", email)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, safe), "wb") as fh:
            fh.write(content_bytes)
        r = await store.update_certification(email, cert_id,
            {"uploaded_file_path": f"/uploads/certs/{email}/{safe}"})
    return _row_to_cert(r)


@router.delete("/me/certifications/{cert_id}/upload-doc", status_code=204)
async def delete_cert_doc(cert_id: str, current_user: dict = Depends(get_current_user)):
    email = current_user["email"]
    cert  = next((c for c in store.get_certifications(email) if c["id"] == cert_id), None)
    if not cert:
        _404("Certificazione non trovata")
    fp = cert.get("uploaded_file_path", "")
    if fp:
        if fp.startswith("sp:"):
            from app.sharepoint import delete_file
            try:
                await delete_file(fp[3:])
            except Exception:
                pass
        else:
            p = os.path.join("/app", fp.lstrip("/"))
            if os.path.exists(p):
                os.remove(p)
        await store.update_certification(email, cert_id, {"uploaded_file_path": ""})


@router.get("/me/certifications/{cert_id}/download-doc")
async def download_cert_doc(
    cert_id: str,
    request: Request,
    token: Optional[str] = Query(default=None, include_in_schema=False),
):
    """
    Scarica l'allegato di una certificazione.
    Supporta il token sia nell'header Authorization sia come query param ?token=
    (necessario quando il browser apre un link diretto senza poter inviare headers).
    """
    from fastapi.responses import FileResponse
    from app.security import decode_token

    # Leggi il token dall'header Authorization oppure dal query param
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        jwt = auth_header[7:]
    elif token:
        jwt = token
    else:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Non autenticato")

    try:
        claims = decode_token(jwt)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token non valido")

    email = claims.get("sub")
    if not email or not store.get_user(email):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Utente non trovato")

    cert = next((c for c in store.get_certifications(email) if c["id"] == cert_id), None)
    if not cert:
        _404("Certificazione non trovata")
    fp = cert.get("uploaded_file_path", "")
    if not fp:
        raise HTTPException(404, "Nessun file allegato")
    if fp.startswith("sp:"):
        from app.sharepoint import get_download_url
        return RedirectResponse(await get_download_url(fp[3:]))
    p = os.path.join("/app", fp.lstrip("/"))
    if not os.path.exists(p):
        raise HTTPException(404, "File non trovato")
    return FileResponse(p, filename=os.path.basename(p), media_type="application/octet-stream")


# ── Credly ────────────────────────────────────────────────────────────────────

@router.get("/certifications/credly/preview")
async def credly_preview(url: str = Query(...), current_user: dict = Depends(get_current_user)) -> Dict:
    m = re.search(r'credly\.com/users/([^/#?]+)', url)
    if not m:
        raise HTTPException(400, "URL Credly non valido")
    username = m.group(1)
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(f"https://www.credly.com/users/{username}/badges.json",
                                headers={"Accept": "application/json"})
    if resp.status_code != 200:
        raise HTTPException(502, f"Impossibile accedere a Credly (HTTP {resp.status_code})")
    raw = resp.json()
    badges_raw = raw if isinstance(raw, list) else raw.get("data", raw.get("badges", []))
    email = current_user["email"]
    existing_ids = {c.get("credly_badge_id","") for c in store.get_certifications(email) if c.get("credly_badge_id")}
    result = []
    for b in badges_raw:
        badge_id = b.get("id","")
        tpl  = b.get("badge_template",{}) or {}
        name = tpl.get("name","")
        if not name:
            continue
        ents = (b.get("issuer") or {}).get("entities",[])
        issuing_org = ents[0].get("entity",{}).get("name","") if ents else ""
        issued_at = b.get("issued_at_date","") or ""
        result.append({
            "credly_badge_id": badge_id, "name": name, "issuing_org": issuing_org,
            "year": int(issued_at[:4]) if len(issued_at) >= 4 else None,
            "expiry_date": b.get("expires_at_date"), "badge_image_url": tpl.get("image_url",""),
            "cert_code": None, "status": "existing" if badge_id in existing_ids else "new",
        })
    return {"username": username, "total": len(result), "badges": result}


@router.post("/certifications/credly/import")
async def credly_import(payload: Dict, current_user: dict = Depends(get_current_user)) -> Dict:
    badges = payload.get("badges", [])
    if not badges:
        raise HTTPException(400, "Nessun badge da importare")
    email = current_user["email"]
    existing = {c.get("credly_badge_id",""): c for c in store.get_certifications(email) if c.get("credly_badge_id")}
    imported = updated = 0
    for b in badges:
        bid = b.get("credly_badge_id","")
        if not bid or not b.get("name"):
            continue
        badge_url = f"https://www.credly.com/badges/{bid}"
        if bid in existing:
            await store.update_certification(email, existing[bid]["id"],
                {"name": b.get("name",""), "issuing_org": b.get("issuing_org",""),
                 "year": str(b.get("year","")), "doc_url": badge_url, "doc_attachment_type": "CREDLY"})
            updated += 1
        else:
            await store.add_certification(email,
                {"name": b["name"], "issuing_org": b.get("issuing_org",""),
                 "year": b.get("year"), "credly_badge_id": bid,
                 "doc_url": badge_url, "doc_attachment_type": "CREDLY", "has_formal_cert": True})
            imported += 1
    return {"imported": imported, "updated": updated, "total": imported + updated}


# ── Cert code suggest ─────────────────────────────────────────────────────────

@router.post("/cert-catalog/suggest-codes")
def cert_catalog_suggest_codes(payload: Dict, current_user: dict = Depends(get_current_user)):
    names: Dict[str,str] = payload.get("names", {})
    if not names:
        return {}
    result = {}
    for cert_id, name in names.items():
        suggestions = store.suggest_cert_codes(name, current_user["email"], limit=1)
        if suggestions and suggestions[0]["score"] >= 0.80:
            b = suggestions[0]
            result[cert_id] = {"name": b["name"], "cert_code": b["cert_code"], "score": round(b["score"],3)}
    return result


# ── CV Hints ──────────────────────────────────────────────────────────────────

@router.get("/me/hints")
def get_my_cv_hints(current_user: dict = Depends(get_current_user)):
    email   = current_user["email"]
    profile = store.get_cv_profile(email) or {}
    hints: dict[str, Any] = {"cert_hints": {}, "skill_hints": [], "experience_hints": {}, "profile_hints": []}
    if not profile.get("title"):
        hints["profile_hints"].append({"field": "title", "label": "Titolo professionale mancante"})
    if not profile.get("summary") or len(profile.get("summary","")) < 80:
        hints["profile_hints"].append({"field": "summary", "label": "Summary assente o troppo breve"})
    if not profile.get("phone"):
        hints["profile_hints"].append({"field": "phone", "label": "Telefono mancante"})
    if not profile.get("linkedin_url"):
        hints["profile_hints"].append({"field": "linkedin_url", "label": "LinkedIn mancante"})
    return hints
