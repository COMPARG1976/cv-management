"""
CV Management — AI Services
Microservice FastAPI per parsing CV tramite OpenAI.
Completamente indipendente dal backend: riceve un file path, restituisce JSON strutturato.
"""
import os
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    upload_dir: str = "/app/uploads"
    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

app = FastAPI(
    title="CV Management — AI Services",
    description="Parsing CV tramite OpenAI. Endpoint: /parse, /health",
    version="0.1.0",
)


# ── Request/Response models ────────────────────────────────────────────────────

class ParseRequest(BaseModel):
    file_path: str          # percorso assoluto del file sul volume condiviso
    document_id: str = ""   # ID del CVDocument (stringa UUID o vuoto)


class ParseResponse(BaseModel):
    document_id: str = ""
    status: str             # "ok" | "error"
    data: dict | None = None
    error: str | None = None


class SuggestRequest(BaseModel):
    cv_data: dict           # dati strutturati del CV (da DB)


class SuggestResponse(BaseModel):
    status: str             # "ok" | "error"
    overall_score: float | None = None
    summary: str | None = None
    suggestions: list | None = None
    error: str | None = None


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
def health():
    return {
        "status": "ok",
        "service": "cv-management-ai",
        "openai_configured": bool(settings.openai_api_key),
    }


# ── Parse endpoint ────────────────────────────────────────────────────────────

@app.post("/parse", response_model=ParseResponse, tags=["parsing"])
async def parse_cv(req: ParseRequest):
    """
    Riceve il path di un file CV (PDF o DOCX), estrae il testo,
    chiama OpenAI per strutturare i dati, restituisce JSON.
    """
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OpenAI API key non configurata")

    full_path = os.path.join(settings.upload_dir, os.path.basename(req.file_path))
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail=f"File non trovato: {full_path}")

    try:
        from app.extractor import extract_text
        from app.parser import parse_with_openai

        text = extract_text(full_path)
        if not text.strip():
            return ParseResponse(document_id=req.document_id, status="error", error="Impossibile estrarre testo dal documento")

        result = await parse_with_openai(text, settings.openai_api_key, settings.openai_model)
        return ParseResponse(document_id=req.document_id, status="ok", data=result)

    except Exception as e:
        return ParseResponse(document_id=req.document_id, status="error", error=str(e))


# ── Suggest endpoint ──────────────────────────────────────────────────────────

@app.post("/suggest", response_model=SuggestResponse, tags=["suggestions"])
async def suggest_cv(req: SuggestRequest):
    """
    Riceve i dati strutturati di un CV (da DB) e restituisce
    suggerimenti di miglioramento generati da OpenAI.
    """
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OpenAI API key non configurata")

    try:
        from app.suggester import suggest_improvements
        result = await suggest_improvements(req.cv_data, settings.openai_api_key, settings.openai_model)
        return SuggestResponse(
            status="ok",
            overall_score=result.get("overall_score"),
            summary=result.get("summary"),
            suggestions=result.get("suggestions", []),
        )
    except Exception as e:
        return SuggestResponse(status="error", error=str(e))
