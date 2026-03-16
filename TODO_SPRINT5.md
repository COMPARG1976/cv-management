# TODO — Sprint 5  (CV Management)

> Creato: 2026-03-16
> Repo: https://github.com/COMPARG1976/cv-management

---

## PRIORITA' ALTA

### 1. Export DOCX — Feature principale

Implementare export CV in formato Word tramite `docxtpl` (gia' aggiunto a requirements.txt).

**Backend (`backend/app/routers/export.py` — da creare)**
```
GET /export/cv/docx?template=standard
```
- Carica CV dell'utente autenticato (stesso query di get_my_cv)
- Carica template da `backend/app/templates/docx/cv_{template}.docx`
- Inietta contesto con tutti i campi (vedi nomi corretti sotto)
- Restituisce `StreamingResponse` con `Content-Disposition: attachment`

**Registrazione in `main.py`**
```python
from app.routers import export
app.include_router(export.router, prefix="/export", tags=["export"])
```

**Template Jinja (`backend/app/templates/docx/cv_standard.docx`)**
- Da generare con `gen_template.py` (script in `backend/app/templates/docx/`)
- Nomi variabili nel contesto da usare nel template:

```
Anagrafica:   full_name, email, phone, linkedin_url, residence_city,
              birth_date, summary, job_title, bu_mashfrog, mashfrog_office,
              hire_date_mashfrog, first_employment_date

Esperienze:   experiences[]
  .company_name, .client_name, .role, .start_date_fmt, .end_date_fmt,
  .project_description, .activities, .skills_csv

Competenze:   skills_hard[], skills_soft[]
  .skill_name, .rating, .rating_stars

Formazione:   educations[]
  .institution, .degree_level, .field_of_study, .graduation_year, .grade

Lingue:       languages[]
  .language_name, .level

Certificazioni: certifications[]
  .name, .cert_code, .issuing_org, .year, .expiry_date, .version

Ruoli:        roles[]
  .title, .company, .start_date_fmt, .end_date_fmt
```

- Le date vanno formattate come stringa nel context builder (es. "01/2023", "Presente")
- `rating_stars` = stringa tipo "★★★★☆" (4/5)

**Referenze — layout paragrafo (NON tabella)**
Nel template Word usare:
```
{%p for exp in experiences %}
[paragrafi del blocco esperienza]
{%p endfor %}
```
I paragrafi tra i due tag si ripetono per ogni esperienza.

**Frontend (`frontend/src/App.jsx`)**
- Aggiungere pulsante "Esporta DOCX" nell'header del CV (accanto al pulsante esistente)
- Chiamata: `GET /export/cv/docx?template=standard` con Authorization header
- Trigger download: `window.URL.createObjectURL(blob)` + click su link temporaneo

**`frontend/src/api.js`**
```javascript
export async function exportCVDocx(token, template = "standard") {
  const res = await fetch(`${API_BASE}/export/cv/docx?template=${template}`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  if (!res.ok) throw new Error("Export fallito");
  return res.blob();
}
```

**TODO futuro: template multipli**
- `cv_compact.docx` — versione ridotta 1 pagina
- `cv_mashfrog.docx` — con logo e colori aziendali (richiede immagine logo)
- UI per selezione template (dropdown nel pulsante export)

---

### 2. Fix login luca.fidenti

Password resettata a `Demo123!` via docker exec. Verificare che funzioni dal frontend.
Se ancora KO: controllare hash nel DB con:
```bash
docker exec cv_db psql -U cv_user -d cv_management \
  -c "SELECT email, password_hash FROM users WHERE email='luca.fidenti@mashfrog.com';"
```
e rigenerare hash con:
```bash
docker exec cv_backend python -c \
  "from app.security import hash_password; print(hash_password('Demo123!'))"
```

---

## PRIORITA' MEDIA

### 3. Pulizia codice hints (opzionale)

Il codice hints e' **disabilitato ma presente**. Decidere se:
- Tenerlo commentato (riattivabile in futuro)
- Rimuoverlo completamente per ridurre complessita'

File coinvolti:
- `frontend/src/App.jsx`: `HintChip` component, `hints` state in MyCVView, prop `hints={}` su tutti i tab
- `frontend/src/api.js`: `getCVHints`
- `backend/app/routers/cv.py`: `GET /me/hints` endpoint
- `ai-services/app/suggester.py`: file non usato (era per AI suggestions)
- `ai-services/app/main.py`: `POST /suggest` endpoint non usato

### 4. Fix record orfano esperienze

Verificare/eliminare record `id=15` (company Mashfrog, `cv_id=11`) che risultava orfano.
```bash
docker exec cv_db psql -U cv_user -d cv_management \
  -c "SELECT id, cv_id, company_name, role FROM \"references\" WHERE id=15;"
```

### 5. Tab Esperienze — verifica filtri frontend

Controllare che il tab Esperienze mostri TUTTI i record del DB senza filtri nascosti in App.jsx.

### 6. UX Diff wizard Step 3

Badge `db_only` nelle esperienze: aggiungere testo esplicativo
"Gia' presente nel tuo profilo — gestiscilo dalla tab Esperienze"

---

## NOTE TECNICHE

- `docxtpl==0.19.0` aggiunto a `backend/requirements.txt` — rebuild backend richiesto
- Template DOCX va incluso nel Docker image (Dockerfile copia `app/` → `app/templates/` inclusa)
- docxtpl usa python-docx internamente; non e' necessario installare python-docx separatamente
- Per blocchi multi-paragrafo: usare `{%p for %}` / `{%p endfor %}` (non `{%tr %}` che e' per tabelle)
- Stop hook Claude Code: ancora irrisolto — richiede `preview_start` ma porta 8082 occupata da Docker
