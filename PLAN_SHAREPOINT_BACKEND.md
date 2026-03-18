# Piano: Migrazione Backend da PostgreSQL a SharePoint + Excel

> Stato: **DA FARE** — In attesa di completamento aggiustamenti UX
> Data redazione: 2026-03-18
> Trigger: post-Sprint 6 o quando la UX è stabile

---

## 1. Risposta rapida: è fattibile?

**Sì**, per ~200 utenti è una soluzione realistica.

Il backend FastAPI continua ad esistere esattamente com'è (stessa API, stessa struttura),
ma al posto di SQLAlchemy + PostgreSQL usa **Microsoft Graph API** per leggere/scrivere
file Excel su SharePoint. Per l'utente finale (e per l'admin non-sviluppatore) i dati
sono file Excel normali, apribili e modificabili da browser o desktop.

---

## 2. Struttura dati proposta

### 2a. File Excel principale — `cv_data.xlsx`
Un singolo file su SharePoint (es. `/sites/CVManagement/Shared Documents/cv_data.xlsx`):

| Sheet | Colonne chiave | Note |
|-------|----------------|------|
| **Users** | `email`, `full_name`, `role`, `is_active`, `bu`, `office`, `hire_date`, `title`, `summary`, `availability`, `phone`, `linkedin_url`, `completeness_pct` | Una riga per persona |
| **Skills** | `user_email`, `skill_name`, `level`, `years_exp`, `category` | N righe per persona |
| **References** | `user_email`, `company_name`, `client_name`, `role`, `start_date`, `end_date`, `project_description`, `activities`, `skills_used` | N righe per persona |
| **Certifications** | `user_email`, `name`, `issuing_org`, `year`, `expiry_date`, `cert_code`, `credly_badge_id`, `badge_image_url`, `credential_url`, `sharepoint_url` | N righe per persona |
| **Languages** | `user_email`, `language_name`, `level` | N righe per persona |
| **Education** | `user_email`, `institution`, `degree_level`, `field_of_study`, `graduation_year`, `grade` | N righe per persona |
| **Passwords** | `user_email`, `hashed_password` | Separato per sicurezza. Solo admin può aprire |

> **Nota sicurezza:** lo sheet Passwords può essere in un file separato (`auth_data.xlsx`)
> con permessi ristretti, accessibile solo al backend.

### 2b. Struttura cartelle SharePoint

```
SharePoint: /sites/CVManagement/Shared Documents/
│
├── cv_data.xlsx                          ← dati strutturati (tutti gli utenti)
├── auth_data.xlsx                        ← password hashed (solo backend)
│
└── users/
    ├── mario.rossi@mashfrog.com/
    │   ├── CV/
    │   │   ├── CV_Mario_Rossi_2026-03.docx
    │   │   └── CV_Mario_Rossi_originale.pdf
    │   └── Certificazioni/
    │       ├── SAP_C_S4FTR_2023.pdf
    │       └── OpenText_5-0158_2024.pdf
    │
    └── anna.bianchi@mashfrog.com/
        ├── CV/
        └── Certificazioni/
```

Ogni cartella ha nome = indirizzo email. Leggibile da tutti, modificabile dal singolo.

---

## 3. Architettura backend (invariata verso l'esterno)

La **stessa API REST** (`/api/v1/...`, stessa autenticazione JWT) continua a funzionare.
Cambia solo il livello di accesso ai dati.

```
Frontend (React)   ─── identico a oggi ───▶  Backend FastAPI
                                                    │
                                              ┌─────▼──────────────────┐
                                              │  DataSource layer       │
                                              │  (oggi: SQLAlchemy)     │
                                              │  (domani: GraphClient)  │
                                              └─────┬──────────────────┘
                                                    │ Microsoft Graph API
                                                    ▼
                                             SharePoint Online
                                             (cv_data.xlsx + cartelle)
```

### Nuovo componente: `SharePointDataSource`

```python
# backend/app/datasource/sharepoint.py
class SharePointDataSource:
    def __init__(self, graph_client):
        self._client = graph_client
        self._cache = {}         # cache in-memory, invalida su ogni write
        self._lock = asyncio.Lock()

    async def get_users(self) -> list[dict]: ...
    async def get_cv(self, user_email: str) -> dict: ...
    async def update_skills(self, user_email, skills): ...
    async def add_certification(self, user_email, cert): ...
    # ecc. — stessa interfaccia che oggi usano i router
```

Il `DataSource` è iniettato come dipendenza FastAPI:
```python
# deps.py
def get_ds() -> SharePointDataSource:
    return app.state.datasource
```

I router cambiano `db: Session = Depends(get_db)` in `ds: SharePointDataSource = Depends(get_ds)`.

---

## 4. Tecnologie necessarie

| Libreria | Scopo | Note |
|----------|-------|------|
| `msgraph-sdk` (Python) | Graph API client ufficiale Microsoft | `pip install msgraph-sdk` |
| `openpyxl` | Lettura/scrittura Excel locale (fallback) | già in requirements |
| `msal` | Auth verso Microsoft (app credentials) | già pianificato per Entra SSO |
| `aiofiles` | Write async su stream | già disponibile |

### Autenticazione Graph API
Usa **Client Credentials flow** (app-to-app, senza utente):
```
Azure App Registration:
  - Permissions: Sites.ReadWrite.All, Files.ReadWrite.All
  - Grant: Admin consent

.env:
  SHAREPOINT_SITE_ID=<guid>
  SHAREPOINT_DRIVE_ID=<guid>
  AZURE_CLIENT_ID=<app-id>
  AZURE_CLIENT_SECRET=<secret>
  AZURE_TENANT_ID=<tenant>
```

---

## 5. Problemi noti e soluzioni

### 5a. Concorrenza scritture (principale rischio)
**Problema:** due utenti che salvano contemporaneamente possono corrompersi a vicenda
le righe nello stesso sheet.

**Soluzione:** lock a livello applicativo + operazioni row-level:
- Ogni write usa il `_lock` dell'istanza DataSource → serializza le scritture
- Graph API supporta `@microsoft.graph.conflictBehavior: replace` per sovrascrittura sicura
- Per 200 utenti con sessioni sporadiche il rischio reale è basso

**Alternativa robusta (se serve):** usare **SharePoint Lists** invece di Excel
(SharePoint Lists sono di fatto tabelle con row-level locking nativo via Graph API).
Excel è più leggibile per i non-tecnici, Liste sono più robuste. Scegliere in fase di impl.

### 5b. Performance
**Problema:** leggere 200 righe via Graph API è più lento di una query SQL.

**Soluzione:** cache in-memory con TTL corto (30s):
```python
async def get_all_users(self):
    if "users" in self._cache and not self._is_stale("users"):
        return self._cache["users"]
    data = await self._fetch_sheet("Users")
    self._cache["users"] = data
    return data
```
Acceptable per use case interno non real-time.

### 5c. Ricerca full-text / filtri complessi
**Problema:** JOIN e WHERE su Excel non esistono — tutto va filtrato in Python.

**Soluzione:** al login/startup fare un unico fetch di tutto il file in memoria,
filtrare con list comprehension. Per 200 utenti × 6 sheet (~5000 righe totali) è
completamente in RAM (< 1MB).

### 5d. No Docker Postgres
**Vantaggio principale:** `docker-compose.yml` perde `db` e `ai-services` (se non serve più AI).
Il backend diventa un singolo container Python leggero. Deploy = `docker run`.

### 5e. Backup e storico
**Vantaggio:** SharePoint ha versioning nativo sui file → ogni modifica salvata ha
uno snapshot automatico. Nessun `pg_dump` necessario.

---

## 6. Cosa rimane invariato

| Componente | Cambia? | Note |
|------------|---------|------|
| Frontend React | ❌ No | Stessa API, zero modifiche |
| Router FastAPI | Minimo | `db` → `ds` nelle dipendenze |
| Schemi Pydantic | ❌ No | Stessa struttura dati |
| Auth JWT | ❌ No | Token locali invariati |
| Auth Entra SSO | ❌ No | Già pianificato Sprint 6, complementare |
| Export Excel/PDF/JSON | ❌ No | Anzi: semplificato, leggono da datasource |
| AI Parsing (Upload CV) | ❌ No | Salva su SharePoint invece che DB |
| Nginx frontend | ❌ No | |

---

## 7. Cosa viene eliminato

- Container **PostgreSQL** (porto 5433)
- Container **ai-services** (se non si usa più AI parsing — opzionale)
- `SQLAlchemy`, `alembic`, `psycopg2` da requirements
- `models.py` (ORM)
- `database.py` (engine, Session)
- `ensure_schema_compatibility()` in main.py
- Volume Docker `postgres_data`

---

## 8. Piano di migrazione (quando si decide di fare)

### Fase 1 — Preparazione (1-2 gg)
1. Creare Azure App Registration con permessi Graph API
2. Creare struttura SharePoint: site, document library, cartella `users/`
3. Creare `cv_data.xlsx` con gli sheet (intestazioni corrette)
4. Esportare dati correnti da PostgreSQL → Excel (script una tantum)

### Fase 2 — Layer DataSource (2-3 gg)
1. Implementare `SharePointDataSource` con cache
2. Implementare `read_sheet()`, `write_row()`, `delete_row()`, `upsert_row()`
3. Test unitari con file Excel locale (senza Graph API)

### Fase 3 — Migrazione router (2-3 gg)
1. Sostituire `Depends(get_db)` con `Depends(get_ds)` in tutti i router
2. Sostituire query SQLAlchemy con chiamate DataSource
3. Test integration con Graph API su tenant di test

### Fase 4 — File upload su SharePoint (1 gg)
1. `POST /upload/cv` → salva file in `users/{email}/CV/` invece che su volume Docker
2. `POST /upload/certifications` → salva in `users/{email}/Certificazioni/`
3. Link di download diretti da SharePoint

### Fase 5 — Cleanup (0.5 gg)
1. Rimuovere container db e ai-services da docker-compose.yml
2. Rimuovere models.py, database.py, SQLAlchemy da requirements
3. Update CLAUDE.md + CONTEXT.md

### Stima totale: ~8-10 giorni lavorativi

---

## 9. Prerequisiti prima di iniziare

- [ ] Microsoft 365 / SharePoint Online attivo per il tenant Mashfrog
- [ ] Azure App Registration con `Sites.ReadWrite.All` e `Files.ReadWrite.All`
- [ ] Admin consent concesso sull'app
- [ ] Identificare SHAREPOINT_SITE_ID e DRIVE_ID del sito target
- [ ] UX stabile (questo lavoro è parcheggiato fino a UX ok)

---

## 10. Alternativa da valutare: SharePoint Lists invece di Excel

Se la concorrenza scritture diventa un problema, SharePoint Lists sono superiori:
- Row-level locking nativo
- Graph API supporta `$filter`, `$select`, `$orderby` (simile a SQL)
- Meno leggibili per un non-tecnico che vuole "vedere tutto"
- Più robusti per scritture concorrenti

**Raccomandazione:** iniziare con Excel (più semplice da gestire per l'utente),
passare a Lists se emergono problemi di concorrenza in produzione.

---

> **Reminder:** questo piano è parcheggiato.
> Completare prima Sprint 6 (SSO + People Analytics + Role Management).
> Poi rivalutare se procedere con questa migrazione o mantenersi su DB.
