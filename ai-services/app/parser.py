"""
Parsing strutturato del testo CV tramite OpenAI con structured outputs.
"""
import json
from openai import AsyncOpenAI

# Schema atteso in output dall'AI
CV_EXTRACTION_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "cv_extraction",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "confidence": {"type": "number"},
                "profile": {
                    "type": "object",
                    "properties": {
                        "full_name":  {"type": ["string", "null"]},
                        "title":      {"type": ["string", "null"]},
                        "summary":    {"type": ["string", "null"]},
                        "phone":      {"type": ["string", "null"]},
                        "email":      {"type": ["string", "null"]},
                        "location":   {"type": ["string", "null"]},
                        "linkedin":   {"type": ["string", "null"]},
                        "confidence": {"type": "number"},
                    },
                    "required": ["full_name", "title", "summary", "phone", "email", "location", "linkedin", "confidence"],
                    "additionalProperties": False,
                },
                "skills": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name":             {"type": "string"},
                            "level":            {"type": ["string", "null"]},  # BASE | INTERMEDIO | AVANZATO | ESPERTO
                            "category":         {"type": ["string", "null"]},  # TECNICA | SOFT | LINGUISTICA
                            "years_experience": {"type": ["number", "null"]},
                            "confidence":       {"type": "number"},
                        },
                        "required": ["name", "level", "category", "years_experience", "confidence"],
                        "additionalProperties": False,
                    },
                },
                "experiences": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "company":     {"type": "string"},
                            "role":        {"type": "string"},
                            "start_date":  {"type": ["string", "null"]},
                            "end_date":    {"type": ["string", "null"]},
                            "is_current":  {"type": "boolean"},
                            "description": {"type": ["string", "null"]},
                            "skills_used": {"type": "array", "items": {"type": "string"}},
                            "confidence":  {"type": "number"},
                        },
                        "required": ["company", "role", "start_date", "end_date", "is_current", "description", "skills_used", "confidence"],
                        "additionalProperties": False,
                    },
                },
                "educations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "institution":      {"type": "string"},
                            "degree_type":      {"type": ["string", "null"]},
                            "field_of_study":   {"type": ["string", "null"]},
                            "graduation_year":  {"type": ["number", "null"]},
                            "grade":            {"type": ["string", "null"]},
                            "confidence":       {"type": "number"},
                        },
                        "required": ["institution", "degree_type", "field_of_study", "graduation_year", "grade", "confidence"],
                        "additionalProperties": False,
                    },
                },
                "certifications": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name":         {"type": "string"},
                            "issuing_org":  {"type": ["string", "null"]},
                            "issue_date":   {"type": ["string", "null"]},
                            "expiry_date":  {"type": ["string", "null"]},
                            "credential_url": {"type": ["string", "null"]},
                            "confidence":   {"type": "number"},
                        },
                        "required": ["name", "issuing_org", "issue_date", "expiry_date", "credential_url", "confidence"],
                        "additionalProperties": False,
                    },
                },
                "languages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "language_name": {"type": "string"},
                            "level":         {"type": ["string", "null"]},  # A1..C2 | MADRELINGUA
                            "confidence":    {"type": "number"},
                        },
                        "required": ["language_name", "level", "confidence"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["confidence", "profile", "skills", "experiences", "educations", "certifications", "languages"],
            "additionalProperties": False,
        },
    },
}

SYSTEM_PROMPT = """
Sei un assistente specializzato nell'estrazione strutturata di dati da curriculum vitae.
Analizza il testo del CV fornito ed estrai tutte le informazioni disponibili nel formato JSON richiesto.

Regole:
- Usa null per informazioni non presenti nel CV, non inventare dati
- Per le date usa formato ISO: "YYYY-MM-DD" o "YYYY-MM" se il giorno è sconosciuto
- Per skill level: BASE, INTERMEDIO, AVANZATO, ESPERTO (scegli il più appropriato dal contesto)
- Per skill category: TECNICA (software, linguaggi, framework), SOFT (comunicazione, leadership), LINGUISTICA (lingue)
- Per language level CEFR: A1, A2, B1, B2, C1, C2, MADRELINGUA
- confidence: valore 0.0-1.0 che indica quanto sei sicuro dell'informazione estratta
- Sii conservativo: confidence alta solo se l'informazione è esplicita nel testo
""".strip()


async def parse_with_openai(cv_text: str, api_key: str, model: str = "gpt-4o") -> dict:
    """
    Chiama OpenAI con structured outputs per estrarre dati strutturati dal testo del CV.
    """
    client = AsyncOpenAI(api_key=api_key)

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": f"Estrai i dati dal seguente CV:\n\n{cv_text[:12000]}"},
        ],
        response_format=CV_EXTRACTION_SCHEMA,
        temperature=0.1,
        timeout=60,
    )

    content = response.choices[0].message.content
    return json.loads(content)
