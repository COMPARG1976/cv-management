"""
Analisi AI del CV e generazione suggerimenti di miglioramento.
"""
import json
from openai import AsyncOpenAI

CV_SUGGESTIONS_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "cv_suggestions",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "overall_score": {
                    "type": "number",
                    "description": "Punteggio qualita CV da 0 a 100"
                },
                "summary": {
                    "type": "string",
                    "description": "Commento generale sintetico sul CV (2-3 frasi)"
                },
                "suggestions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "section": {
                                "type": "string",
                                "description": "Sezione CV: profile | skills | experiences | certifications | educations | languages"
                            },
                            "type": {
                                "type": "string",
                                "description": "Tipo suggerimento: expand_description | missing_data | add_skill | add_certification | update_cert_code | add_language"
                            },
                            "priority": {
                                "type": "string",
                                "description": "Priorita: HIGH | MEDIUM | LOW"
                            },
                            "title": {
                                "type": "string",
                                "description": "Titolo breve del suggerimento (max 80 caratteri)"
                            },
                            "description": {
                                "type": "string",
                                "description": "Spiegazione dettagliata del suggerimento con esempio concreto"
                            },
                            "item_ref": {
                                "type": ["string", "null"],
                                "description": "Riferimento all'elemento specifico (es. nome azienda, nome certificazione)"
                            }
                        },
                        "required": ["section", "type", "priority", "title", "description", "item_ref"],
                        "additionalProperties": False
                    }
                }
            },
            "required": ["overall_score", "summary", "suggestions"],
            "additionalProperties": False
        }
    }
}

SUGGESTIONS_SYSTEM_PROMPT = """
Sei un esperto HR e career coach specializzato in CV per professionisti IT del settore consulting.
Analizza il CV fornito e produci suggerimenti concreti e actionable per migliorarlo.

Controlla in particolare:

PROFILO:
- Il summary/titolo e' presente e sufficientemente dettagliato (almeno 3 righe)?
- Mancano contatti importanti (linkedin, telefono, localita')?

ESPERIENZE:
- Ogni esperienza ha una descrizione? E' abbastanza dettagliata (almeno 2-3 righe)?
- Le tecnologie/tool menzionati nelle descrizioni sono presenti anche nelle skill?
- Ci sono esperienze senza data?

COMPETENZE:
- Mancano skill tecniche che si evincono dalle esperienze ma non sono listate?
- Il livello di ogni skill e' indicato?

CERTIFICAZIONI:
- Le certificazioni hanno il codice identificativo (es. AZ-900, PMP, AWS-SAA)?
- Le certificazioni hanno l'URL di verifica?
- Dall'esperienza si evincono certificazioni che potrebbero essere state conseguite ma non sono elencate?

FORMAZIONE:
- Mancano informazioni (anno, voto, indirizzo)?

LINGUE:
- Se il profilo e' di un professionista IT italiano, e' strano che manchi l'inglese?

Produci SOLO suggerimenti utili e specifici. Non inventare informazioni non deducibili dal CV.
Priorita' HIGH: impatto diretto sulla leggibilita' e completezza del CV.
Priorita' MEDIUM: miglioramenti significativi ma non bloccanti.
Priorita' LOW: ottimizzazioni minori.
""".strip()


async def suggest_improvements(cv_data: dict, api_key: str, model: str = "gpt-4o") -> dict:
    """
    Analizza i dati strutturati del CV e restituisce suggerimenti di miglioramento.
    """
    client = AsyncOpenAI(api_key=api_key)

    cv_text = json.dumps(cv_data, ensure_ascii=False, indent=2)

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SUGGESTIONS_SYSTEM_PROMPT},
            {"role": "user", "content": f"Analizza questo CV e produci suggerimenti di miglioramento:\n\n{cv_text[:14000]}"},
        ],
        response_format=CV_SUGGESTIONS_SCHEMA,
        temperature=0.3,
        timeout=60,
    )

    content = response.choices[0].message.content
    return json.loads(content)
