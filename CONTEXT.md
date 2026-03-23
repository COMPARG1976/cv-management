# CV Management System — Contesto Architetturale

> Documento di riferimento per decisioni tecniche e pattern architetturali
> Data: 2026-03-23 (aggiornato Sprint 7 — Excel-only backend)

---

## 1. Panoramica Architettura

```
┌─────────────────────────────────────────────────────────────────┐
│            Browser (Utente / Admin)                             │
│            DEV: http://localhost:8082                           │
│            PRD: https://cvapp.mashfrogcloud.com                    │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTPS :443 (PRD) / HTTP :8082 (DEV)
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│              Frontend Container (React + Nginx)                  │
│  • SPA React 18 + Vite 5                                        │
│  • Nginx: SPA routing fallback + /api proxy                     │
│  • /api/* → backend:8000 (rete Docker interna)                  │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP :8000 (interno Docker)
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Backend Container (FastAPI)                     │
│  • Auth JWT + Entra SSO, RBAC, CV CRUD                          │
│  • Storage: STORE in-memory → persist su master_cv.xlsx         │
│  • WAL: _dirty flag + retry ogni 30s se SP offline              │
│  • Backup automatico ogni 2h → master_cv_backup.xlsx            │
│  • Chiama AI service per parsing (HTTP interno ai-services:8000) │
└───────────────────────┬─────────────────────────────────────────┘
                        │ HTTP ai-services:8000 (interno Docker)
                        ▼
┌──────────────────────────────┐    ┌────────────────────────────┐
│   AI Services Container      │    │  Microsoft SharePoint       │
│   • FastAPI + OpenAI SDK     │    │  (Microsoft Graph API)      │
│   • Parsing PDF/DOCX → JSON  │◀──▶│  • master_cv.xlsx (store)  │
│   • Volume condiviso uploads │    │  • CV/ e CER/ (allegati)   │
└──────────────────────────────┘    │  • CV_TEMPLATE_JINJA/      │
                                    └────────────────────────────┘
```

### Note rete AWS (produzione)
- HTTPS termina all'**ALB** (Application Load Balancer) — i container parlano HTTP internamente
- Container-to-container: HTTP sulla rete VPC privata (nessun TLS interno necessario)
- SharePoint: raggiunto via HTTPS dal backend tramite Microsoft Graph API

### Porte in DEV locale
| Porta Host | Servizio | Note |
|------------|----------|------|
| **8082** | Frontend CV Mgmt | (8080=IT_RESOURCE_MGMT) |
| **8002** | Backend CV Mgmt | (8000=IT_RM, 8001=YATO) |
| **8003** | AI Services CV Mgmt | |

---

## 2. Decisioni Tecniche e Razionale

### 2.1 React + Vite (non Next.js)
**Decisione:** React 18 + Vite 5, stessa scelta di IT_RESOURCE_MGMT.
**Motivazione:**
- Node.js non installato localmente → entrambi i progetti girano via Docker
- Consistenza con IT_RESOURCE_MGMT (riuso componenti, pattern identici)
- Vite: build veloci, HMR ottimale in sviluppo Docker
- Next.js aggiungerebbe SSR/SSG non necessario per questa SPA aziendale interna

### 2.2 SharePoint + Excel come unico storage (no PostgreSQL)
**Decisione (Sprint 6):** `master_cv.xlsx` su SharePoint via Microsoft Graph API.
**Motivazione:**
- ~200 utenti, no transazioni concorrenti ad alta frequenza → Excel è sufficiente
- L'organizzazione usa già SharePoint/Microsoft 365 → zero infrastruttura aggiuntiva
- Backup implicito via versioning SharePoint
- Admin può ispezionare/editare i dati senza strumenti DB
- Eliminata dipendenza da PostgreSQL, RDS, Alembic, SQLAlchemy

**Pattern STORE:**
- In-memory dict `STORE` caricato all'avvio da SP
- Ogni write: aggiorna STORE in RAM → `persist()` → upload su SP
- Lock `asyncio.Lock` serializza le scritture
- WAL: `_dirty=True` se upload SP fallisce → retry loop ogni 30s
- `/health` espone `sharepoint_dirty` per monitoring

### 2.3 AI Service come Container Separato
**Decisione:** Microservice FastAPI separato dal backend principale.
**Motivazione:**
- Dipendenze pesanti isolate: OpenAI SDK, PyMuPDF, python-docx
- Sostituibile senza toccare il backend (cambio provider AI)
- Scalabile indipendentemente (parsing è CPU/IO intensivo)
- Volume `uploads_data` condiviso tra backend e ai-services

### 2.4 Autenticazione: JWT locale + Entra ID
**Implementazione attuale:**
- `AUTH_PROVIDER=entra` → SSO Microsoft Entra ID (produzione)
- `AUTH_PROVIDER=fake` → backdoor locale con `BACKDOOR_PASSWORD` (dev/emergenza)
- Backend valida token Entra via JWKS endpoint Azure
- Auto-provisioning utente al primo login SSO se email non in STORE

### 2.5 API Pubblica Versionata (`/api/v1/`)
**Decisione:** Prefisso di versione su tutte le route pubbliche.
**Motivazione:**
- IT_RESOURCE_MGMT e altri servizi consumano queste API
- `/api/v1/resources/search` → endpoint chiave per integrazione inter-app
- Versioning previene breaking changes

### 2.6 Suggest-Codes: fonte da Certification (non catalogo centrale)
**Decisione (Sprint 5):** Eliminata tabella `cert_catalog` centralizzata.
**Razionale:**
- La vera fonte sono le certificazioni già inserite da utenti reali con `cert_code` valorizzato
- Zero manutenzione, autoarricchimento nel tempo, nessun false positive
- `POST /cv/cert-catalog/suggest-codes`: Jaccard + SequenceMatcher, soglia ≥ 0.80

---

## 3. Struttura Dati Excel (STORE)

```
master_cv.xlsx
├── Staff          — utenti + profilo CV (merge Users + CVProfiles)
├── Skills         — competenze per email
├── Educations     — formazione per email
├── Experiences    — esperienze lavorative per email
├── Certifications — certificazioni per email
│     ├── id, email, name, issuing_org, cert_code, version, year
│     ├── expiry_date, has_formal_cert, doc_attachment_type (NONE|CREDLY|URL)
│     ├── doc_url, credly_badge_id, badge_image_url
│     └── uploaded_file_path (sp:STAFF_DATA.../CER/nome.cognome_CER_...pdf)
├── Languages      — lingue per email
├── Documents      — documenti CV caricati per email
├── REF_BU         — master data Business Unit
├── REF_CertTags   — master data aree/cluster certificazioni
└── REF_Skills     — master data tassonomia skill
```

### Regola `doc_attachment_type`
- **NONE** — nessun badge/link esterno (può comunque avere allegato PDF via `uploaded_file_path`)
- **CREDLY** — badge Credly collegato (`credly_badge_id` valorizzato)
- **URL** — URL pubblico esterno (`doc_url` valorizzato)
- L'allegato fisico SP è sempre indicato da `uploaded_file_path` (indipendente dal tipo)

### Naming file SharePoint
```
CV/   nome.cognome_CV_<primi15chars>.<ext>
CER/  nome.cognome_CER_<codice>_<primi15chars>.<ext>
```

---

## 4. Pattern Backend (FastAPI)

```
backend/app/
├── main.py          # lifespan, CORS, router include, health, WAL loop, backup loop
├── excel_store.py   # STORE in-memory, persist(), CRUD per ogni entità
├── sharepoint.py    # Microsoft Graph API: upload, download, delete, get_url
├── settings.py      # pydantic-settings: env vars
├── schemas.py       # Pydantic v2 request/response (no ORM)
├── security.py      # JWT HS256, decode_token, hash_password
├── deps.py          # get_current_user(), require_roles()
└── routers/
    ├── auth.py      # POST /auth/login, GET /auth/config, Entra exchange
    ├── users.py     # CRUD utenti (solo ADMIN)
    ├── cv.py        # CRUD CV, suggest-codes, Credly import, cert merge
    ├── search.py    # Ricerca avanzata, API pubblica /api/v1/resources
    ├── upload.py    # Upload CV/DOCX → AI parse → diff; thumbnail PNG (LRU cache 50)
    └── export.py    # Export DOCX (docxtpl), template validation
```

### Cache Thumbnail
- LRU in-memory, max 50 entry (~2.5 MB RAM)
- Key: `cert_id`; invalidata su upload nuovo file o rimozione allegato
- Endpoint: `GET /upload/documents/cert/{id}/thumbnail?token=`

---

## 5. Pattern Frontend (React + Vite)

- **App.jsx** monolitico (SPA, no routing React Router)
- **useState** per state management locale
- **api.js** wrapper fetch con Bearer token e error extraction
- **styles.css** design system pure CSS

### Named imports React (obbligatorio)
```js
import { useState, useRef, useEffect } from "react";  // mai React.useState
```

### Struttura viste
```
LOGIN → HOME
  ├── (USER) Il Mio CV
  │     ├── Anagrafica, Formazione, Competenze, Esperienze
  │     ├── Certificazioni (con thumbnail PDF, tag SP/Credly/URL, merge Credly)
  │     ├── Lingue
  │     └── Carica CV (wizard AI: upload → diff → apply)
  │
  └── (ADMIN) Pannello Admin
        ├── Utenti (lista + gestione ruolo)
        ├── People Analytics (ricerca multi-criterio, export)
        └── Impostazioni (Aggiorna template — solo giuseppe.comparetti)
```

---

## 6. AI Service — Pattern di Chiamata

```
Frontend      Backend           AI Service      OpenAI
   │              │                  │              │
   │──POST /upload/cv──▶│            │              │
   │              │──save file──▶ volume            │
   │              │──POST /parse────▶│              │
   │              │                  │──API call────▶│
   │              │◀──structured JSON│◀─────────────│
   │◀──{diff}─────│                  │              │
   │              │                  │              │
   │──POST /upload/apply──▶│         │              │
   │◀──{cv_updated}────────│         │              │
```

---

## 7. API Pubblica — Contratto Inter-App

```
GET /api/v1/resources/search
  ?skills=Java,AWS&skill_op=AND&min_level=INTERMEDIO&available=true
  → [{ id, full_name, title, skills, availability_status }]

GET /api/v1/resources/{user_id}
  → { id, full_name, title, summary, skills[], experiences[], ... }

GET /api/v1/resources
  ?q=nome_cognome&page=1&size=20
  → { items: [...], total: int }
```
**Header:** `Authorization: Bearer <jwt-token>`

---

## 8. SSO Microsoft Entra ID

```
Frontend                    Backend                  Azure AD
   │──click "Login Aziendale"──▶│                        │
   │                           │──redirect ─────────────▶│
   │◀────────────── login form ──────────────────────────│
   │──credenziali──────────────────────────────────────▶│
   │◀────────────── authorization code ──────────────────│
   │──POST /auth/entra/exchange──▶│                       │
   │                           │──validate via JWKS ─────▶│
   │◀──{access_token, user}────│◀────────────────────────│
```

### Variabili Entra richieste
```
ENTRA_TENANT_ID, ENTRA_CLIENT_ID, ENTRA_CLIENT_SECRET, ENTRA_AUDIENCE
ENTRA_REDIRECT_URI=https://cvapp.mashfrogcloud.com/auth/callback  # PRD
```

---

## 9. Evoluzione / Roadmap

| Versione | Feature | Stato |
|----------|---------|-------|
| v1 Sprint 1–5 | Core CV + AI parsing | ✅ Completato |
| v1.1 Sprint 6 | SharePoint backend, SSO Entra, backup | ✅ Completato |
| v1.2 Sprint 7 | WAL, template validation, cert import analysis | ✅ Completato |
| v1.3 Sprint 8+ | Merge Credly+PDF, thumbnail cert, tag separati | ✅ Completato |
| Futuro | ZIP export CV+CERT selezionati | 📋 TODO_EXPORT_ZIP.md |
| Futuro | Import cert da CERT_ANALYSIS (fase 2) | ⏳ Dopo revisione umana |
| Futuro | Migrazione repo → org aziendale + branch `dev/claude` | 📋 Pianificato |
| v2 | Deploy AWS (EC2 + ALB HTTPS) | 📋 Pianificato |

---

## 10. Riferimenti

- **Progetto di riferimento:** `C:\20.PROGETTI_CLAUDE_CODE\20.IT_RESOURCE_MGMT`
- Pattern autenticazione: `security.py` (JWT HS256 + passlib)
- Pattern Docker Compose: Nginx + FastAPI + volume condiviso
- Pattern Nginx SPA: `frontend/nginx.conf` (fallback + /api proxy)
- SharePoint API: Microsoft Graph `drives/{id}/root:/{path}:/content`
