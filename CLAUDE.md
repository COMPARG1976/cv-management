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
| ORM | SQLAlchemy | 2.0 |
| DB driver | psycopg2-binary | 2.9 |
| Database | PostgreSQL | 15-alpine |
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

## Note per Claude Code

- Il DB PostgreSQL è sulla porta host **5433** (non 5432)
- Il backend è sulla porta host **8002** (non 8000)
- Per il frontend React: **non usare `npm run dev` in Bash** → Node.js non è in PATH locale; usare Docker
- Vite dev server sulla porta **5174** se avviato in Docker per sviluppo
- AI service chiama OpenAI: assicurarsi che `OPENAI_API_KEY` sia in `.env`
- Volume `uploads_data` condiviso tra `backend` e `ai-services`
- Riferirsi a `CONTEXT.md` per decisioni architetturali già prese
- Riferirsi a `REQUIREMENTS.md` per scope e priorità feature
