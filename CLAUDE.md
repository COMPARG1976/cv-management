# CV Management System — Istruzioni per Claude Code

> Questo file fornisce contesto e istruzioni operative per Claude Code.
> Aggiornare ad ogni sprint completato.

---

## Progetto

**Nome:** CV Management System
**Directory:** `C:\20.PROGETTI_CLAUDE_CODE\40.CV_MANAGEMENT`
**Scopo:** Applicazione interna per gestione curriculum ~200 risorse. Modulare e riusabile (le API `/resources/search` sono consumate da IT_RESOURCE_MGMT e altri servizi).

---

## Stack e Versioni

| Componente | Tecnologia | Versione |
|------------|------------|---------|
| Backend | FastAPI | 0.116+ |
| Python | cpython | 3.12 |
| Storage | openpyxl (Excel su SharePoint) | 3.1+ |
| Auth | Microsoft Entra ID (MSAL) + backdoor locale | — |
| Frontend | React | 18.x |
| Build tool | Vite | 5.x |
| AI | OpenAI API | gpt-4o |
| Container | Docker Compose | v2 |
| Proxy | Nginx | 1.27 |

---

## Porte (non modificare senza aggiornare CLAUDE.md del workspace)

| Porta Host | Container | Servizio |
|------------|-----------|---------|
| **5433** | 5432 | PostgreSQL |
| **8002** | 8000 | Backend FastAPI |
| **8003** | 8000 | AI Services |
| **8082** | 80 | Frontend Nginx |

---

## Comandi Operativi

```bash
# Percorso progetto
PROJECT=/c/20.PROGETTI_CLAUDE_CODE/40.CV_MANAGEMENT

# Avvio completo
docker compose -f $PROJECT/docker-compose.yml up --build -d

# Stop
docker compose -f $PROJECT/docker-compose.yml down

# Log backend
docker logs cv_mgmt_backend -f

# Log AI service
docker logs cv_mgmt_ai -f

# Log frontend/nginx
docker logs cv_mgmt_frontend -f

# Health check
curl -s http://localhost:8002/health
curl -s http://localhost:8003/health

# Backend solo (sviluppo, senza Docker — richiede .env e DB avviato)
cd $PROJECT/backend
DATABASE_URL=postgresql+psycopg2://cv_user:cv_password@localhost:5433/cv_management \
  python -m uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload

# AI service solo (sviluppo)
cd $PROJECT/ai-services
python -m uvicorn app.main:app --host 0.0.0.0 --port 8003 --reload
```

---

## Struttura Directory

```
40.CV_MANAGEMENT/
├── CLAUDE.md                    ← questo file
├── REQUIREMENTS.md              ← requisiti funzionali e tecnici
├── CONTEXT.md                   ← architettura e decisioni tecniche
├── docker-compose.yml
├── .env                         ← NON committare (da .env.example)
├── .env.example
├── .gitignore
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py              ← entry point FastAPI, lifespan, health
│       ├── database.py          ← engine, SessionLocal, get_db
│       ├── models.py            ← SQLAlchemy ORM models
│       ├── schemas.py           ← Pydantic v2 schemas
│       ├── security.py          ← JWT, password hashing
│       ├── deps.py              ← get_current_user, require_roles
│       ├── crud.py              ← helper CRUD
│       ├── seed.py              ← dati demo
│       └── routers/
│           ├── auth.py          ← /auth/login, /auth/config
│           ├── users.py         ← /users (ADMIN only)
│           ├── cv.py            ← /cv (USER: proprio, ADMIN: tutti)
│           ├── skills.py        ← /skills (tassonomia, autocomplete)
│           ├── search.py        ← /search, /api/v1/resources/*
│           ├── upload.py        ← /upload, /parse
│           └── export.py        ← /export/excel, /export/pdf
│
├── frontend/
│   ├── Dockerfile
│   ├── nginx.conf               ← SPA routing + /api proxy
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       ├── main.jsx
│       ├── App.jsx              ← componente principale (SPA monolitica)
│       ├── api.js               ← fetch wrapper con auth
│       ├── styles.css           ← design system pure CSS
│       └── components/
│           └── FuzzySelect.jsx  ← dropdown con ricerca fuzzy (riuso da IT_RM)
│
└── ai-services/
    ├── Dockerfile
    ├── requirements.txt
    └── app/
        ├── main.py              ← FastAPI AI service, /health, /parse
        ├── parser.py            ← logica parsing OpenAI
        └── extractor.py        ← estrazione testo da PDF/DOCX
```

---

## Regole di Sviluppo

### Pattern da seguire (copiare da IT_RESOURCE_MGMT dove possibile)
1. **Auth/Security**: copia `security.py` e `deps.py` da IT_RESOURCE_MGMT, adatta i ruoli
2. **DDL migration**: usa `ensure_schema_compatibility()` in `main.py` (no Alembic)
3. **Seeding**: `seed.py` con admin + utenti demo, password da `.env`
4. **Health check**: `GET /health → {"status": "ok"}` su tutti i servizi
5. **CORS**: da env var `CORS_ORIGINS` (split su `,`)
6. **Error format**: `{"detail": "messaggio"}` (FastAPI default)
7. **Frontend API URL**: `VITE_API_URL=/api` passato come build arg Docker

### Stile codice
- Python: type hints su tutti gli endpoint, docstring solo dove non ovvio
- Pydantic v2: `model_config = ConfigDict(from_attributes=True)` per ORM models
- SQLAlchemy 2.0: session context manager (`with SessionLocal() as db:`) dove possibile
- React: functional components + hooks, no class components
- CSS: BEM-like naming, variabili CSS per colori/spacing

### Test (da aggiungere per ogni sprint)
- pytest + httpx[AsyncClient] per endpoint test
- Fixture `db_session` con rollback automatico
- Test file: `backend/tests/test_<router>.py`

---

## Variabili .env Obbligatorie

```
POSTGRES_DB=cv_management
POSTGRES_USER=cv_user
POSTGRES_PASSWORD=<scegliere>
SECRET_KEY=<openssl rand -hex 32>
OPENAI_API_KEY=sk-...
AUTH_PROVIDER=fake
```

---

## Sprint Completati

### Sprint 1 — Fondamenta ✅ (2026-03-14)
- Docker Compose: 4 container (db, backend, ai-services, frontend)
- Backend: auth JWT, modelli ORM completi, schema DB, seed utenti demo
- Frontend: login, home con tile nav, struttura SPA
- AI Service: health check, endpoint `/parse` con OpenAI gpt-4o
- API pubblica `/api/v1/resources/search` e `/api/v1/resources`

### Sprint 2 — CV Completo + UX ✅ (2026-03-14)
- Backend: `GET/PUT /cv/me` → `CVFullResponse` (include campi User)
- Backend: `_compute_completeness()` dinamico (non persistito)
- Backend: PUT su ogni sotto-risorsa (skills, educations, languages, references, certifications)
- Backend: `GET /cv/skills/suggest` e `GET /cv/certifications/suggest` (autocomplete)
- Frontend: 7 tab CV (Anagrafica, Formazione, Competenze, Esperienze, Certificazioni, Lingue, Carica CV)
- Frontend: pulsanti ✏ Modifica sempre visibili su ogni item e su Anagrafica (no global toggle)
- Frontend: `AutocompleteInput` generico con debounce 300ms per skill e cert_code
- Frontend: data/ora ultima modifica sotto il nome nella header del CV
- Frontend: barra completezza CV calcolata dinamicamente
- Dati Mashfrog: `hire_date_mashfrog`, `mashfrog_office`, `bu_mashfrog` in AnagraficaTab
- Certificazioni: `doc_attachment_type` (NONE/CREDLY/URL/SHAREPOINT), `doc_url`

---

### Sprint 3 — CV Upload con AI Parsing + Diff Review ✅ (2026-03-15)
- Backend: `POST /upload/cv` — upload PDF/DOCX, chiamata AI service, calcolo diff campo per campo
- Backend: `POST /upload/apply` — applica selezioni utente al DB (idempotente: skip duplicati per tutte le sezioni)
- Backend: `compute_diff()` — fuzzy matching su 5 sezioni (skills, references, educations, certifications, languages)
- Backend: mapping `degree_type_raw → DegreeLevel`, `level → rating(1-5)`, `category TECNICA→HARD`
- Frontend: `UploadTab` — wizard 4 step (Upload → Processing → Review Diff → Success)
- Frontend: `ReviewStep` — diff field-by-field con radio DB/AI/Manual, default conservativo "Mantieni DB"
- Frontend: `ItemsSection` — sezioni tabellari (items new/changed/unchanged/db_only con badge colorati)
- Frontend: `ProfileSection` — campi scalari del profilo con controllo per-field
- Fix: sostituito `React.useState/useRef/useEffect` con hook named (mancava import React namespace)

### Sprint 4 — Sort + Credly + Hints ✅ (2026-03-16)
- Ordinamento referenze: end_date DESC NULLS FIRST + start_date DESC (sentinella "9999-99")
- Hint chips DB-driven: infrastruttura presente, disabilitata (riattivabile)
- Export DOCX: `docxtpl==0.19.0` in requirements.txt, `export.py` router registrato
- Password sync: `_sync_all_passwords` in lifespan per consistenza tutti gli utenti
- Credly preview: `GET /cv/certifications/credly/preview?url=...` — anteprima badge profilo pubblico

### Sprint 5 — Cert Suggest Refactoring ✅ (2026-03-17)
- Eliminata tabella `cert_catalog` centralizzata (modello `CertCatalogEntry`, JSON, script scraping)
- `POST /cv/cert-catalog/suggest-codes` — nuova fonte: `Certification WHERE cert_code IS NOT NULL` (per-utente)
  - Algoritmo: Jaccard token-based + SequenceMatcher, soglia 0.80
  - Stop words ridotte — ruoli (administrator, analyst, user...) NON sono stop words
- Rimossi: `GET /cv/cert-catalog/search`, `POST /cv/cert-catalog/refresh`
- Rimossi: `scripts/update_opentext_certs.py`, `backend/app/cert_catalog.json`
- `populate_cert_catalog()` rimossa da `main.py`

### Sprint 6 — Production Readiness + Excel Backend ✅ (2026-03-18)
- **Backend Excel-only**: rimosso PostgreSQL, `master_cv.xlsx` su SharePoint è unico storage
- **SSO Microsoft Entra ID**: login con account aziendale, backdoor locale per admin
- **Sheet Staff**: merge `Users` + `CVProfiles` in un unico sheet (backward-compat fallback)
- **Fix completeness score**: backend ritorna 0–1 (era 0–100), frontend già moltiplicava × 100
- **Fix Stars**: `Number(value)` nel componente (valori Excel arrivano come stringa)
- **Fix delete_document**: ritorna `True`/`False` invece di `None` (evita 404 spurio)
- **Upload CV**: parametro `ai_update` per scegliere se attivare AI parsing; file salvato su SP `CV/{email}/`
- **Download CV**: `GET /upload/documents/{id}/download` — tenta SP poi volume locale
- **Template DOCX da SharePoint**: `GET /export/templates` legge da SP `CV_TEMPLATE_JINJA` (fallback locale)
- **Backup ogni 2 ore**: `asyncio.create_task(_backup_loop())` in lifespan, tracciamento timestamp in-memory
- **Retry upload SP 423**: 4 tentativi con backoff 3s/6s/9s/12s su file locked
- **Cert hint threshold**: alzato da 0.3 a 0.55 (Jaccard + SequenceMatcher)

### Sprint 7 — WAL + Template Validation + Cert Import Analysis ✅ (2026-03-19)
- **WAL (Write-Ahead Log)**: `_dirty` flag in `excel_store.py`; `persist()` ritorna `bool`; `retry_persist_if_dirty()` acquista write lock e riprova; loop background ogni 30s in `main.py`; `/health` espone `sharepoint_dirty`
- **Fix `str(None)` → `"None"`**: bug storage in `add_experience`, `add_education`, `add_certification` — pattern `str(data.get("field","") or "")`
- **Template DOCX validation**: `GET /export/templates/validate` — scarica template SP, valida struttura DOCX, render con mock context Jinja2; tile "Aggiorna template" visibile solo a `giuseppe.comparetti`
- **Naming CV/CERT**: convenzione `nome.cognome_CV_<first15>.<ext>` e `nome.cognome_CER_<code>_<first15>.<ext>`; struttura flat `CV/` e `CER/` (non per-persona)
- **Script `_import_certs_analysis.py`**: analisi SAP_CERTIFICAZIONI_2026.xlsx + 133 PDF in CERTIFICAZIONI_EX_CARTELLA_MADERA; output `CERT_ANALYSIS_20260319.xlsx` (7 sheet); AI verify con gpt-4o/gpt-4o-mini (122 PDF: 90 OK, 32 mismatch); costo ~$0.15
- **Script `_update_cert_analysis.py`**: aggiorna CERT_ANALYSIS senza rieseguire AI; applica correzioni da PERSONE_SENZA_EMAIL (nuova mail, inverti nome/cognome); colori VERDE/ROSSO/GRIGIO/AZZURRO; genera righe azzurre corrette per ogni rossa
- **TODO futuro**: ZIP export (script legge colonna "export" da master_cv_copy, crea due zip CV+CERT)
- **TODO futuro**: fase 2 `_import_certs_analysis.py --generate-store` (dopo revisione umana CERT_ANALYSIS)

---

## REGOLA CRITICA — master_cv.xlsx

> **⛔ VIETATO manipolare `master_cv.xlsx` direttamente** (lettura/scrittura via openpyxl, script one-shot, ecc.)
> senza esplicito assenso di giuseppe.comparetti.
>
> Il file è l'unico storage di produzione. Modifiche dirette bypassano lock, WAL, backup e audit trail.
> **Qualsiasi scrittura deve passare ESCLUSIVAMENTE dalle API dell'applicazione** (`excel_store.py` tramite i router FastAPI).
> Unica eccezione: script di import una-tantum approvati esplicitamente (es. `_import_certs_analysis.py`
> fase 2 — da eseguire solo dopo revisione umana del file CERT_ANALYSIS).

---

## Note per Claude Code

- Il DB PostgreSQL è sulla porta host **5433** (non 5432)
- Il backend è sulla porta host **8002** (non 8000)
- Per il frontend React: **non usare `npm run dev` in Bash** → Node.js non è in PATH locale; usare Docker
- Vite dev server sulla porta **5174** se avviato in Docker per sviluppo
- AI service chiama OpenAI: assicurarsi che `OPENAI_API_KEY` sia in `.env`
- Volume `uploads_data` condiviso tra `backend` e `ai-services`
- Riferirsi a `CONTEXT.md` per decisioni architetturali già prese
- Riferirsi a `REQUIREMENTS.md` per scope e priorità feature
