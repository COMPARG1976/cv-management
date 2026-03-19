"""
Parsing strutturato del testo CV tramite OpenAI con structured outputs.
"""
import json
from openai import AsyncOpenAI

# Schema atteso in output dall'AI
# Nota: i campi "confidence" e "skills_used" sono stati rimossi dallo schema.
# Non vengono mai usati dal diff engine del backend e generavano token di output inutili
# (+30-40% latenza). Il modello rimane gpt-4o per massima fedeltà nel copiare il testo.
CV_EXTRACTION_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "cv_extraction",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
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
                    },
                    "required": ["full_name", "title", "summary", "phone", "email", "location", "linkedin"],
                    "additionalProperties": False,
                },
                "skills": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name":     {"type": "string"},
                            "level":    {"type": ["string", "null"]},  # BASE | INTERMEDIO | AVANZATO | ESPERTO
                            "category": {"type": ["string", "null"]},  # TECNICA | SOFT | LINGUISTICA
                        },
                        "required": ["name", "level", "category"],
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
                            "activities":  {"type": ["string", "null"]},
                        },
                        "required": ["company", "role", "start_date", "end_date", "is_current", "description", "activities"],
                        "additionalProperties": False,
                    },
                },
                "educations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "institution":     {"type": "string"},
                            "degree_type":     {"type": ["string", "null"]},
                            "field_of_study":  {"type": ["string", "null"]},
                            "graduation_year": {"type": ["number", "null"]},
                            "grade":           {"type": ["string", "null"]},
                        },
                        "required": ["institution", "degree_type", "field_of_study", "graduation_year", "grade"],
                        "additionalProperties": False,
                    },
                },
                "certifications": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name":           {"type": "string"},
                            "issuing_org":    {"type": ["string", "null"]},
                            "issue_date":     {"type": ["string", "null"]},
                            "expiry_date":    {"type": ["string", "null"]},
                            "credential_url": {"type": ["string", "null"]},
                        },
                        "required": ["name", "issuing_org", "issue_date", "expiry_date", "credential_url"],
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
                        },
                        "required": ["language_name", "level"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["profile", "skills", "experiences", "educations", "certifications", "languages"],
            "additionalProperties": False,
        },
    },
}

SYSTEM_PROMPT = """
Sei un assistente specializzato nell'estrazione strutturata di dati da curriculum vitae.
Analizza il testo del CV fornito ed estrai tutte le informazioni disponibili nel formato JSON richiesto.

Regole generali:
- Usa null per informazioni non presenti nel CV, non inventare dati
- Per le date usa formato ISO: "YYYY-MM-DD" o "YYYY-MM" se il giorno è sconosciuto
- Per skill level: BASE, INTERMEDIO, AVANZATO, ESPERTO (scegli il più appropriato dal contesto)
- Per skill category: TECNICA (software, linguaggi, framework), SOFT (comunicazione, leadership), LINGUISTICA (lingue)
- Per language level CEFR: A1, A2, B1, B2, C1, C2, MADRELINGUA

Regola CRITICA per le competenze (skills):
- Estrai ESATTAMENTE 15 competenze (o meno se nel CV ne sono presenti meno di 15)
- Seleziona le competenze che ricorrono più frequentemente nel CV e che meglio caratterizzano il profilo
- Dai priorità a: linguaggi di programmazione, framework, piattaforme, tool chiave, metodologie principali
- Escludi competenze banali, generiche o non rilevanti (es. "Microsoft Office", "email", "Internet")
- Usa il nome più breve e canonico (es. "REST" non "RESTful Web Services", "SQL" non "SQL Databases")
- Rispetta esattamente la stessa ortografia/maiuscolo del testo originale del CV

Regola CRITICA per le esperienze/referenze — campo description e activities:
- Copia il testo ESATTAMENTE come appare nel CV, parola per parola, senza omettere nulla
- NON riassumere, NON sintetizzare, NON parafrasare, NON accorciare
- Se il CV descrive un progetto in 10 righe, il campo description deve contenere tutte e 10 le righe
- Preserva elenchi puntati, attività, tecnologie, contesto del progetto esattamente come scritti
- La fedeltà al testo originale è più importante della brevità
- Campo activities: copia le attività/responsabilità specifiche esattamente come scritte nel CV
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
            # 12.000 char ≈ 3.000 token: copre anche CV da 20+ pagine.
        # Oltre questa soglia il testo è solitamente boilerplate/footer.
        {"role": "user",   "content": f"Estrai i dati dal seguente CV:\n\n{cv_text[:12000]}"},
        ],
        response_format=CV_EXTRACTION_SCHEMA,
        temperature=0.1,
        timeout=60,
    )

    content = response.choices[0].message.content
    return json.loads(content)
