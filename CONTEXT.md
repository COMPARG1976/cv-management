# CV Management System — Contesto Architetturale

> Documento di riferimento per decisioni tecniche e pattern architetturali
> Data: 2026-03-17 (aggiornato Sprint 5)

---

## 1. Panoramica Architettura

```
┌─────────────────────────────────────────────────────────────────┐
│                    Browser (Utente / Admin)                     │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP :8082
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│              Frontend Container (React + Nginx)                  │
│  • SPA React 18 + Vite 5                                        │
│  • Nginx: SPA routing fallback + /api proxy                     │
│  • /api/* → backend:8000 (container network)                    │
└────────────────────────┬────────────────────────────────────────┘
                         │ /api → HTTP :8000 (interno)
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Backend Container (FastAPI)                     │
│  • Auth (JWT locale + Entra SSO), RBAC, CV CRUD                 │
│  • Ricerca, Export, People Analytics                            │
│  • REST API versioned: /api/v1/                                 │
│  • Upload gestione file (volume condiviso)                      │
│  • Chiama AI service per parsing (interno :8000)                │
└───────────┬─────────────────────┬───────────────────────────────┘
            │                     │
            │ SQLAlchemy          │ HTTP ai-services:8000
            ▼                     ▼
┌───────────────────┐   ┌─────────────────────────────────────────┐
│  DB Container     │   │        AI Services Container             │
│  PostgreSQL 15    │   │  • FastAPI + OpenAI SDK                 │
│  porta host 5433  │   │  • Parsing PDF/DOCX → JSON strutturato  │
│                   │   │  • Indipendente, sostituibile           │
└───────────────────┘   └─────────────────────────────────────────┘
            │                     │
            └─────────────────────┘
                   Volume: uploads_data
                   (documenti CV caricati)
```

### Porte Host (coesistenza con altri progetti)
| Porta Host | Servizio | Note |
|------------|----------|------|
| **8082** | Frontend CV Mgmt | (8080=IT_RESOURCE_MGMT) |
| **8002** | Backend CV Mgmt | (8000=IT_RM, 8001=YATO) |
| **8003** | AI Services CV Mgmt | nuovo |
| **5433** | PostgreSQL CV Mgmt | (5432=IT_RESOURCE_MGMT) |

---

## 2. Decisioni Tecniche e Razionale

### 2.1 React + Vite (non Next.js)
**Decisione:** React 18 + Vite 5, stessa scelta di IT_RESOURCE_MGMT.
**Motivazione:**
- Node.js non installato localmente → entrambi i progetti girano via Docker
- Consistenza di pattern con IT_RESOURCE_MGMT (facilita riuso codice componenti)
- Vite: build velocissimi, HMR ottimale in sviluppo Docker
- Next.js aggiungerebbe SSR/SSG che non serve per questa SPA aziendale interna

### 2.2 PostgreSQL (non SQLite)
**Decisione:** PostgreSQL 15-alpine.
**Motivazione:**
- 200 utenti: write concorrenti richiedono MVCC di Postgres
- Full-text search nativo (`tsvector`, `GIN index`) per ricerca skill
- Array nativo (`TEXT[]`) per tag skill (pattern già usato in IT_RESOURCE_MGMT)
- JSONB per metadati AI parsing (confidenze, raw output)
- ENUM per livelli skill, disponibilità, stato utente
- Migrazione da SQLite a Postgres è onerosa; meglio partire da Postgres

### 2.3 AI Service come Container Separato
**Decisione:** Microservice FastAPI separato anziché librerie integrate nel backend.
**Motivazione:**
- Dipendenze pesanti isolate (OpenAI SDK, PyMuPDF per PDF, python-docx)
- Sostituibile senza toccare il backend (es. cambio provider AI)
- Scalabile indipendentemente (il parsing è CPU/IO intensivo)
- Backend rimane leggero e veloce
- Pattern: backend chiama AI service su rete Docker interna

### 2.4 Schema Dati Relazionale (non JSONB puro)
**Decisione:** Tabelle relazionali per ogni sezione del CV.
**Motivazione:**
- Queryability: `SELECT * FROM cv_skills WHERE skill_name = 'Java'` → efficiente
- Ricerca per skill richiede join, non scan JSONB
- Indexability: indici su skill_name, level, category
- JSONB limitato a metadati AI (raw output, confidenze) — non alla struttura principale
- Alternativa JSONB-only: facile da scrivere, difficile da interrogare → scartata

### 2.5 Autenticazione: JWT locale + Entra ID (Sprint 6)
**Decisione:** Auth locale JWT in v1 (Sprint 1-5), migrazione a Entra ID in Sprint 6.
**Motivazione (v1 locale):**
- Sviluppo rapido senza dipendenze Azure
- Pattern identico a IT_RESOURCE_MGMT → riuso codice security.py
**Predisposizione Entra (già presente):**
- Endpoint `/auth/entra/exchange` per token exchange
- Claims mapping configurabile (`preferred_username`, `email`)
- `AUTH_PROVIDER` env var per switch senza code change
**Sprint 6 — implementazione completa:**
- MSAL flow lato frontend (redirect → Microsoft → callback con code)
- Backend valida token Entra con JWKS endpoint Azure
- Creazione utente automatica al primo login SSO se email non esiste nel DB

### 2.6 API Pubblica Versionata (`/api/v1/`)
**Decisione:** Prefisso di versione su tutte le route.
**Motivazione:**
- IT_RESOURCE_MGMT e altri servizi consumeranno queste API
- Versioning previene breaking changes quando si aggiorna il contratto
- `/api/v1/resources/search` → endpoint chiave per integrazione inter-app

### 2.7 Suggest-Codes: fonte da Certification (non catalogo centrale)
**Decisione Sprint 5:** Eliminata tabella `cert_catalog` centralizzata.
**Razionale:**
- Mantenere un catalogo aggiornato (SAP, OpenText, Databricks) richiedeva scraping fragile e soggetto a errori
- La vera fonte di verità sono le certificazioni già inserite da utenti reali con `cert_code` valorizzato
- Vantaggi: zero manutenzione, autoarricchimento nel tempo, nessun false positive da dati errati
- `POST /cv/cert-catalog/suggest-codes` ora fa query `DISTINCT (name, cert_code)` su `Certification WHERE cert_code IS NOT NULL`
- Stesso algoritmo: Jaccard + SequenceMatcher, soglia ≥ 0.80

---

## 3. Schema Database (Concettuale)

```
User (1)──────────────────(1) CV
 │                              │
 │                              ├── CVSkill (N)
 │                              │     ├── skill_name
 │                              │     ├── level (ENUM)
 │                              │     ├── years_exp
 │                              │     └── category (ENUM)
 │                              │
 │                              ├── Reference (N)     ← tabella "references" (quotare in SQL raw)
 │                              │     ├── company_name, client_name, role
 │                              │     ├── start_date, end_date  (formato "YYYY-MM", sentinella "9999-99" per "Presente")
 │                              │     ├── project_description, activities
 │                              │     └── skills_used (TEXT[])
 │                              │
 │                              ├── Education (N)
 │                              │     ├── institution, degree_level (ENUM)
 │                              │     ├── field_of_study
 │                              │     └── graduation_year, grade
 │                              │
 │                              ├── Certification (N)
 │                              │     ├── name, issuing_org
 │                              │     ├── year (int), expiry_date
 │                              │     ├── cert_code                ← codice esame (es. C_S4FTR_2023)
 │                              │     ├── credly_badge_id          ← ID badge Credly
 │                              │     ├── badge_image_url          ← URL immagine badge
 │                              │     └── credential_url
 │                              │
 │                              ├── Language (N)
 │                              │     ├── language_name
 │                              │     └── level (ENUM: A1→C2)
 │                              │
 │                              └── CVDocument (N)
 │                                    ├── original_filename
 │                                    ├── storage_path
 │                                    ├── parsed_at
 │                                    └── ai_raw_output (JSONB)
 │
 └── (is_active, role, created_at, updated_at)

SkillTaxonomy (tassonomia centralizzata)
 ├── name (unique, indexed)
 ├── category
 ├── aliases (TEXT[])
 └── usage_count (aggiornato da trigger/query)
```

### Enum Types
```sql
CREATE TYPE user_role AS ENUM ('USER', 'ADMIN');
CREATE TYPE skill_level AS ENUM ('BASE', 'INTERMEDIO', 'AVANZATO', 'ESPERTO');
CREATE TYPE skill_category AS ENUM ('TECNICA', 'LINGUISTICA', 'SOFT', 'CERTIFICAZIONE');
CREATE TYPE language_level AS ENUM ('A1', 'A2', 'B1', 'B2', 'C1', 'C2', 'MADRELINGUA');
CREATE TYPE availability_status AS ENUM ('DISPONIBILE', 'OCCUPATO', 'IN_USCITA');
```

---

## 4. Pattern Backend (FastAPI)

Identici a IT_RESOURCE_MGMT per garantire consistenza:

```
backend/
├── app/
│   ├── main.py          # lifespan, CORS, router include, health
│   ├── database.py      # engine, SessionLocal, get_db()
│   ├── models.py        # SQLAlchemy ORM (tutti i modelli)
│   ├── schemas.py       # Pydantic v2 request/response
│   ├── security.py      # JWT, password hashing, token decode
│   ├── deps.py          # get_current_user(), require_roles()
│   ├── crud.py          # helper CRUD riutilizzabili
│   ├── seed.py          # dati demo (admin + utenti test)
│   └── routers/
│       ├── auth.py      # POST /auth/login, GET /auth/config, Entra exchange
│       ├── users.py     # CRUD utenti (solo ADMIN), PUT /users/{id}/role
│       ├── cv.py        # CRUD CV (USER: proprio, ADMIN: tutti), suggest-codes
│       ├── skills.py    # Tassonomia skill, autocomplete
│       ├── search.py    # Ricerca avanzata (ADMIN + API pubblica)
│       ├── upload.py    # Upload documenti, trigger AI
│       └── export.py    # Export Excel, PDF (docxtpl), JSON batch
```

### Middleware Stack
```python
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS)
# Futuro: rate limiting su /api/v1/resources/* (slowapi)
```

### RBAC Enforcement
```python
# Solo il proprio CV (USER)
def get_cv_or_403(cv_id, current_user, db):
    cv = db.get(CV, cv_id)
    if current_user.role == Role.USER and cv.user_id != current_user.id:
        raise HTTPException(403)
    return cv

# Solo ADMIN
@router.get("/admin/users")
def list_users(user=Depends(require_roles(Role.ADMIN)), db=Depends(get_db)):
    ...

# Promozione ruolo — solo ADMIN
@router.put("/users/{id}/role")
def update_role(user=Depends(require_roles(Role.ADMIN)), ...):
    ...
```

---

## 5. Pattern Frontend (React + Vite)

Stesso approccio di IT_RESOURCE_MGMT:
- **App.jsx** monolitico per v1 (refactoring in componenti nella v2)
- **useState** per state management locale (no Redux)
- **api.js** wrapper fetch con auth header e error extraction
- **styles.css** design system pure CSS (palette allineata a IT_RESOURCE_MGMT)
- **Vite build-time** per VITE_API_URL

### Struttura Viste
```
LOGIN → HOME
              ├── (USER) Il Mio CV
              │     ├── Anagrafica
              │     ├── Skill
              │     ├── Esperienze
              │     ├── Formazione
              │     ├── Certificazioni
              │     ├── Lingue
              │     └── Upload CV (wizard AI)
              │
              └── (ADMIN) Pannello Admin
                    ├── Utenti (lista + gestione + modifica ruolo)
                    ├── People Analytics (nuovo Sprint 6)
                    │     ├── Ricerca multi-criterio
                    │     ├── Tabella risultati + selezione
                    │     ├── Export Excel / PDF / JSON
                    │     └── Dashboard skill & completezza
                    └── Ricerca per Skill
```

---

## 6. AI Service — Pattern di Chiamata

### Flusso Upload + Parsing
```
Frontend                Backend              AI Service        OpenAI
   │                       │                     │               │
   │──POST /upload ────────▶│                     │               │
   │  (multipart PDF)      │──save file──▶ volume │               │
   │                       │                     │               │
   │                       │──POST /parse ───────▶│               │
   │                       │  {file_path}         │──API call ────▶│
   │                       │                     │◀──JSON struct──│
   │◀──{job_id, status}────│◀──{structured_data}─│               │
   │                       │──save ai_result──▶ DB│               │
   │                       │                     │               │
   │──GET /parse/{job_id}──▶│                     │               │
   │◀──{status, data}──────│                     │               │
```

### Output AI Strutturato (esempio)
```json
{
  "confidence": 0.92,
  "profile": {
    "full_name": "Mario Rossi",
    "title": "Senior Software Engineer",
    "summary": "...",
    "confidence": 0.98
  },
  "skills": [
    {"name": "Python", "level": "ESPERTO", "years": 8, "confidence": 0.95},
    {"name": "Docker", "level": "AVANZATO", "years": 4, "confidence": 0.88}
  ],
  "experiences": [...],
  "education": [...],
  "certifications": [...],
  "languages": [...]
}
```

---

## 7. API Pubblica — Contratto Inter-App

```
GET /api/v1/resources/search
  ?skills=Java,AWS&skill_op=AND
  &min_level=INTERMEDIO
  &available=true
  → [{ id, full_name, title, skills, availability_status }]

GET /api/v1/resources/{user_id}
  → { id, full_name, title, summary, skills[], experiences[], ... }

GET /api/v1/resources
  ?q=nome_cognome&page=1&size=20
  → { items: [...], total: int }

GET /api/v1/skills
  ?q=java&limit=20
  → [{ name, category, usage_count }]
```

**Header richiesto:** `Authorization: Bearer <jwt-token>`

---

## 8. Suggest-Codes — Architettura (Sprint 5, refactored)

### Fonte dati
Nessun catalogo centralizzato. La fonte sono le certificazioni già inserite da utenti nel DB:

```sql
SELECT DISTINCT name, cert_code
FROM certifications
WHERE cert_code IS NOT NULL AND cert_code != ''
```

Man mano che gli utenti popolano i propri CV con `cert_code` valorizzato, la base di suggerimento si arricchisce automaticamente.

### Endpoint
```
POST /cv/cert-catalog/suggest-codes
     Body: {"names": {"cert_id": "Nome certificazione da suggerire"}}
     → {"cert_id": {"name": "...", "cert_code": "...", "score": 0.93}}

     Algoritmo: max(SequenceMatcher ratio, Jaccard token score)
     Soglia minima: 0.80
     Stop words: certified, opentext, for, the, in, of, a, an, using, managing,
                 configuring, implementing, technology, sap
     Ruoli (administrator, business, user, analyst, developer) NON sono stop words
```

### Decisione architetturale: perché niente catalogo centrale
- Un catalogo centrale richiede scraping periodico di fonti eterogenee (SAP, OpenText, Databricks, Credly) soggette a cambiare struttura
- I codici scraped possono essere errati o non aggiornati
- La "fonte di verità" sono i codici che gli utenti già usano e validano
- Approccio autosufficiente: zero dipendenze esterne, migliora con l'uso

---

## 9. SSO Microsoft Entra ID — Piano Sprint 6

### Flusso MSAL (Authorization Code)
```
Frontend                    Backend                  Azure AD
   │                           │                        │
   │──click "Login Microsoft"──▶│                        │
   │                           │──redirect ─────────────▶│
   │◀──────────────────────────────────── login form ────│
   │──credenziali Microsoft────────────────────────────▶│
   │◀──────────────────── authorization code ────────────│
   │──POST /auth/entra/exchange──▶│                       │
   │  {code, redirect_uri}       │──validate token via───▶│
   │                           │  JWKS endpoint          │
   │◀──{access_token, user} ───│◀───────────────────────│
```

### Configurazione `.env` per Entra
```
AUTH_PROVIDER=entra
AZURE_TENANT_ID=<tenant-id>
AZURE_CLIENT_ID=<app-client-id>
AZURE_CLIENT_SECRET=<secret>   # solo backend (confidential client)
```

### Mapping Claims → User DB
| Claim Entra | Campo User DB | Note |
|-------------|---------------|------|
| `preferred_username` / `email` | `email` | lookup principale |
| `name` | `full_name` | usato solo alla creazione |
| `oid` | `azure_oid` (futura colonna) | identificativo stabile |

---

## 10. People Analytics — Piano Sprint 6

### Backend: nuovi endpoint in `search.py` o `analytics.py`
```
GET /admin/analytics/people
    ?skill=Java&skill_level=AVANZATO&cert=C_S4FTR&lang=EN&bu=&available=true
    &q=cognome
    → {total: int, items: [{user_id, full_name, bu, skills[], certs[], ...}]}

POST /admin/analytics/export/excel
    Body: {user_ids: [1,2,3,...], fields: ["name","skills","certs",...]}
    → StreamingResponse (.xlsx)

POST /admin/analytics/export/json
    Body: {user_ids: [1,2,3,...]}
    → JSON array CV completi

POST /admin/analytics/export/pdf-batch
    Body: {user_ids: [1,2,3,...]}
    → StreamingResponse (.zip con PDF per utente)
```

### Frontend: PeopleAnalyticsView
- Pannello filtri laterale (skill multi-select, livello, cert, lingua, BU, disponibilità)
- Tabella risultati con checkbox per selezione multipla
- Barra azioni contestuale quando ≥1 selezionato: "Export Excel", "Export PDF", "Export JSON"
- Sezione dashboard collassabile: top skill, completezza CV, distribuzione disponibilità

---

## 11. Migrazione/Evoluzione Prevista

| Versione | Aggiunta | Note |
|----------|----------|------|
| v1 (Sprint 1-5) | Core CV + AI parsing | Completato |
| v1.1 (Sprint 6) | SSO Entra ID | Switch `AUTH_PROVIDER=entra` |
| v1.1 (Sprint 6) | People Analytics + Export batch | Nuovo tile Admin |
| v1.1 (Sprint 6) | Role management ADMIN | PUT /users/{id}/role |
| v1.1 (Sprint 6) | SharePoint link su allegati | Campo `sharepoint_url` |
| v2 | Upload diretto su SharePoint (Graph API) | OAuth2 on-behalf-of |
| v2 | Notifiche email (certificazioni in scadenza) | SMTP + scheduler |
| v3 | Storage S3 per upload | Replace volume con boto3 |
| v3 | API key per service-to-service | Header `X-API-Key` |
| v4 | Workflow approvazione CV | State machine su CV |

---

## 12. Riferimenti

- **Progetto di riferimento:** `C:\20.PROGETTI_CLAUDE_CODE\20.IT_RESOURCE_MGMT`
- Pattern autenticazione: `20.IT_RESOURCE_MGMT/backend/app/security.py`
- Pattern RBAC: `20.IT_RESOURCE_MGMT/backend/app/deps.py`
- Pattern DDL migration: `20.IT_RESOURCE_MGMT/backend/app/main.py` (ensure_schema_compatibility)
- Pattern Docker Compose: `20.IT_RESOURCE_MGMT/docker-compose.yml`
- Pattern Nginx SPA: `20.IT_RESOURCE_MGMT/frontend/nginx.conf`
