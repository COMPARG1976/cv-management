# CV Management System — Requisiti

> Versione: 0.5 — Documento di riferimento per lo sviluppo iterativo
> Data: 2026-03-17
> Stato: In evoluzione (Sprint 6 pianificato)

---

## 1. Requisiti Funzionali

### FR-AUTH — Autenticazione e Autorizzazione

| ID | Requisito | Priorità |
|----|-----------|----------|
| FR-AUTH-001 | Login con username (email) e password | MUST |
| FR-AUTH-002 | Sessione basata su JWT con scadenza configurabile (default 12h) | MUST |
| FR-AUTH-003 | Controllo accessi basato su ruoli: USER e ADMIN | MUST |
| FR-AUTH-004 | SSO Microsoft Entra ID (Azure AD) — login con account aziendale Microsoft | MUST |
| FR-AUTH-005 | Logout con invalidazione token lato client | MUST |
| FR-AUTH-006 | Refresh token (futura implementazione) | COULD |
| FR-AUTH-007 | Un utente ADMIN può promuovere/degradare altri utenti a ADMIN o USER | MUST |

**Ruoli applicativi:**
- **USER**: può gestire solo il proprio CV
- **ADMIN**: accesso completo a tutti i CV, ricerca, analytics, export, gestione utenti (incluso promozione ad ADMIN)

---

### FR-CV — Gestione CV (ruolo USER)

#### FR-CV-PROFILE — Profilo e Anagrafica
| ID | Requisito | Priorità |
|----|-----------|----------|
| FR-CV-001 | Visualizzare e modificare dati anagrafici (nome, cognome, email, telefono, LinkedIn) | MUST |
| FR-CV-002 | Caricare foto profilo | COULD |
| FR-CV-003 | Impostare titolo professionale e sommario/bio | MUST |
| FR-CV-004 | Indicare disponibilità (disponibile, occupato, in uscita) | SHOULD |

#### FR-CV-SKILLS — Competenze
| ID | Requisito | Priorità |
|----|-----------|----------|
| FR-CV-010 | Aggiungere/rimuovere skill con livello (base, intermedio, avanzato, esperto) | MUST |
| FR-CV-011 | Categorizzare le skill (tecnica, linguistica, soft skill, certificazione) | MUST |
| FR-CV-012 | Indicare anni di esperienza per skill | SHOULD |
| FR-CV-013 | Ricerca autocomplete sulle skill esistenti in azienda | SHOULD |

#### FR-CV-EXP — Esperienze Lavorative
| ID | Requisito | Priorità |
|----|-----------|----------|
| FR-CV-020 | Aggiungere/modificare/eliminare esperienze lavorative | MUST |
| FR-CV-021 | Ogni esperienza: azienda, ruolo, data inizio/fine, descrizione, skill usate | MUST |
| FR-CV-022 | Supporto posizione corrente (data fine = null) | MUST |
| FR-CV-023 | Ordinamento cronologico inverso automatico | MUST |

#### FR-CV-EDU — Formazione
| ID | Requisito | Priorità |
|----|-----------|----------|
| FR-CV-030 | Aggiungere/modificare/eliminare titoli di studio | MUST |
| FR-CV-031 | Ogni titolo: istituto, tipo laurea/diploma, campo, anno conseguimento, voto | MUST |

#### FR-CV-CERT — Certificazioni
| ID | Requisito | Priorità |
|----|-----------|----------|
| FR-CV-040 | Aggiungere/modificare/eliminare certificazioni | MUST |
| FR-CV-041 | Ogni certificazione: nome, ente, data conseguimento, data scadenza, URL badge | MUST |
| FR-CV-042 | Alert visivo per certificazioni scadute o in scadenza (< 60 gg) | SHOULD |
| FR-CV-043 | Campo `cert_code` (codice esame ufficiale, es. C_S4FTR_2023) | SHOULD |
| FR-CV-044 | Campo `badge_image_url` per immagine badge Credly/Accredible | SHOULD |
| FR-CV-045 | Campo `credly_badge_id` per collegamento diretto al badge Credly | SHOULD |
| FR-CV-046 | Suggerimento codice esame per cert esistenti senza codice, basato su cert già presenti nel DB con codice (fuzzy match Jaccard ≥ 0.80) | SHOULD |
| FR-CV-047 | Hint chip "Codice esame: X_XXXX" per cert senza codice se match trovato | COULD |
| FR-CV-048 | Anteprima badge Credly con immagine, nome, emissione e scadenza | COULD |
| FR-CV-049 | Allegato certificazione su SharePoint — link a documento condiviso | SHOULD |

#### FR-CV-LANG — Lingue
| ID | Requisito | Priorità |
|----|-----------|----------|
| FR-CV-050 | Aggiungere/modificare/eliminare lingue con livello CEFR (A1→C2) | MUST |

#### FR-CV-UPLOAD — Upload e AI Parsing
| ID | Requisito | Priorità |
|----|-----------|----------|
| FR-CV-060 | Caricare file CV esistente (PDF, DOCX, max 10 MB) | MUST |
| FR-CV-061 | Il sistema estrae dati strutturati dal CV tramite AI (OpenAI) | MUST |
| FR-CV-062 | L'utente visualizza i dati estratti e li valida/corregge prima del salvataggio | MUST |
| FR-CV-063 | Indicatore di confidenza AI su ogni sezione estratta | SHOULD |
| FR-CV-064 | Possibilità di ri-fare il parsing di un documento già caricato | SHOULD |
| FR-CV-065 | Salvataggio documento originale per download futuro | SHOULD |

#### FR-CV-EXPORT — Export CV Personale
| ID | Requisito | Priorità |
|----|-----------|----------|
| FR-CV-070 | Export del proprio CV in PDF (template aziendale) | SHOULD |
| FR-CV-071 | Anteprima del CV formattato | SHOULD |

#### FR-CV-COMPLETENESS — Completezza
| ID | Requisito | Priorità |
|----|-----------|----------|
| FR-CV-080 | Indicatore di completezza CV (percentuale e sezioni mancanti) | SHOULD |
| FR-CV-081 | Notifica visiva quando il CV non è aggiornato da > 6 mesi | COULD |

---

### FR-ADMIN — Funzionalità Amministrative

#### FR-ADMIN-USERS — Gestione Utenti
| ID | Requisito | Priorità |
|----|-----------|----------|
| FR-ADMIN-001 | Vedere lista di tutti gli utenti con stato CV (completo/incompleto/assente) | MUST |
| FR-ADMIN-002 | Creare nuovo utente (anagrafica + ruolo + password temporanea) | MUST |
| FR-ADMIN-003 | Modificare ruolo utente (USER ↔ ADMIN) | MUST |
| FR-ADMIN-004 | Disattivare/riattivare utente (soft delete) | MUST |
| FR-ADMIN-005 | Reset password utente | SHOULD |
| FR-ADMIN-006 | UI per rigenerare/inviare password temporanee (tramite `init_passwords.py`) | COULD |

#### FR-ADMIN-ANALYTICS — People Analytics (nuovo tile Admin)
| ID | Requisito | Priorità |
|----|-----------|----------|
| FR-ADMIN-PA-001 | Tile dedicato "People Analytics" nella home Admin | MUST |
| FR-ADMIN-PA-002 | Ricerca/filtro per: nome, skill, livello skill, certificazione, lingua, disponibilità, BU, sede, anni esperienza | MUST |
| FR-ADMIN-PA-003 | Tabella risultati con colonne configurabili (nome, BU, sede, skill principali, cert, disponibilità) | MUST |
| FR-ADMIN-PA-004 | Selezione multipla di righe risultato per export batch | MUST |
| FR-ADMIN-PA-005 | Export Excel (.xlsx) dei risultati selezionati con dati completi | MUST |
| FR-ADMIN-PA-006 | Export PDF CV per ogni utente selezionato (zip batch se multipli) | SHOULD |
| FR-ADMIN-PA-007 | Export JSON strutturato dei CV selezionati (per integrazione con altri sistemi) | MUST |
| FR-ADMIN-PA-008 | Dashboard skill: top skill aziendali per frequenza | SHOULD |
| FR-ADMIN-PA-009 | Heatmap/distribuzione livelli per skill | COULD |
| FR-ADMIN-PA-010 | Metriche di completezza CV aziendali | SHOULD |
| FR-ADMIN-PA-011 | Gap analysis: skill richieste vs. presenti | COULD |

#### FR-ADMIN-SEARCH — Ricerca e Filtri (integrata in People Analytics)
| ID | Requisito | Priorità |
|----|-----------|----------|
| FR-ADMIN-010 | Ricerca full-text su tutti i CV (nome, skill, ruolo, azienda) | MUST |
| FR-ADMIN-011 | Filtro per skill (singola o combinazione AND/OR) | MUST |
| FR-ADMIN-012 | Filtro per livello skill (es. "Java avanzato o esperto") | MUST |
| FR-ADMIN-013 | Filtro per anni di esperienza totale | SHOULD |
| FR-ADMIN-014 | Filtro per certificazione | SHOULD |
| FR-ADMIN-015 | Filtro per disponibilità | SHOULD |
| FR-ADMIN-016 | Filtro per lingua | SHOULD |
| FR-ADMIN-017 | Filtro per BU e sede Mashfrog | SHOULD |
| FR-ADMIN-018 | Salvataggio filtri/ricerche frequenti | COULD |

#### FR-ADMIN-EXPORT — Export Dati
| ID | Requisito | Priorità |
|----|-----------|----------|
| FR-ADMIN-030 | Export risultati ricerca in Excel (.xlsx) | MUST |
| FR-ADMIN-031 | Export CV singolo o batch in PDF | SHOULD |
| FR-ADMIN-032 | Export CV singolo o batch in JSON strutturato | MUST |
| FR-ADMIN-033 | Export anagrafica utenti completa | SHOULD |

#### FR-ADMIN-SHAREPOINT — Integrazione Allegati
| ID | Requisito | Priorità |
|----|-----------|----------|
| FR-ADMIN-SP-001 | Collegare una certificazione a un documento su SharePoint (URL) | MUST |
| FR-ADMIN-SP-002 | Apertura documento SharePoint da link nel CV | MUST |
| FR-ADMIN-SP-003 | Upload diretto su SharePoint via Microsoft Graph API | COULD |
| FR-ADMIN-SP-004 | Sincronizzazione automatica allegati SharePoint | COULD |

---

### FR-API — API Pubblica per Integrazione Inter-App

> Queste API sono consumate da altre applicazioni aziendali (es. IT_RESOURCE_MGMT)

| ID | Requisito | Priorità |
|----|-----------|----------|
| FR-API-001 | `GET /api/v1/resources/search?skills=Java,AWS&level=avanzato` — ricerca risorse per skill | MUST |
| FR-API-002 | `GET /api/v1/resources/{id}` — profilo completo di una risorsa | MUST |
| FR-API-003 | `GET /api/v1/resources` — lista risorse con filtri (nome, disponibilità) | MUST |
| FR-API-004 | `GET /api/v1/skills` — tassonomia skill aziendale | MUST |
| FR-API-005 | Autenticazione API via Bearer token (stesso JWT del login) | MUST |
| FR-API-006 | Documentazione OpenAPI/Swagger automatica | MUST |
| FR-API-007 | Rate limiting sulle API pubbliche | COULD |

---

### FR-AI — Servizi AI

| ID | Requisito | Priorità |
|----|-----------|----------|
| FR-AI-001 | Parsing documento CV (PDF/DOCX) tramite OpenAI API | MUST |
| FR-AI-002 | Estrazione strutturata: anagrafica, skill, esperienze, formazione, certificazioni, lingue | MUST |
| FR-AI-003 | Score di confidenza (0-1) per ogni sezione estratta | SHOULD |
| FR-AI-004 | Mapping automatico skill estratte alla tassonomia aziendale | SHOULD |
| FR-AI-005 | Health check endpoint | MUST |
| FR-AI-006 | Timeout parsing: 60 secondi max | MUST |
| FR-AI-007 | Gestione errori graceful (AI non disponibile → utente inserisce manualmente) | MUST |

---

## 2. Requisiti Non Funzionali

### NFR-PERF — Performance
| ID | Requisito |
|----|-----------|
| NFR-PERF-001 | Ricerca risorse per skill: risposta < 2 secondi per 200 utenti |
| NFR-PERF-002 | Salvataggio/caricamento CV: < 1 secondo |
| NFR-PERF-003 | AI parsing documento: < 60 secondi (async con feedback progress) |
| NFR-PERF-004 | Export Excel 200 righe: < 5 secondi |
| NFR-PERF-005 | Export JSON batch 50 CV: < 10 secondi |

### NFR-SEC — Sicurezza
| ID | Requisito |
|----|-----------|
| NFR-SEC-001 | Password hashate con pbkdf2_sha256 (min 600.000 iterazioni) |
| NFR-SEC-002 | JWT con scadenza configurabile, signature HS256 |
| NFR-SEC-003 | CORS configurato per origini specifiche |
| NFR-SEC-004 | Validazione MIME type e dimensione upload file |
| NFR-SEC-005 | Nessun dato sensibile nei log applicativi |
| NFR-SEC-006 | HTTPS in produzione (configurazione Nginx) |
| NFR-SEC-007 | Un utente USER può accedere solo ai propri dati CV |
| NFR-SEC-008 | Solo un ADMIN può promuovere altri utenti ad ADMIN |
| NFR-SEC-009 | Token Microsoft Entra validato con chiavi pubbliche JWKS di Azure |

### NFR-MOD — Modularità e Riusabilità
| ID | Requisito |
|----|-----------|
| NFR-MOD-001 | API `/resources/search` e `/resources/{id}` consumabili da IT_RESOURCE_MGMT |
| NFR-MOD-002 | Tassonomia skill centralizzata, usata da tutte le app aziendali |
| NFR-MOD-003 | Backend stateless — scalabile orizzontalmente |
| NFR-MOD-004 | AI service indipendente — sostituibile senza modificare il backend |

### NFR-OPS — Operatività
| ID | Requisito |
|----|-----------|
| NFR-OPS-001 | Containerizzazione completa con Docker Compose |
| NFR-OPS-002 | Health check su tutti i servizi |
| NFR-OPS-003 | Volume persistente per dati DB e upload |
| NFR-OPS-004 | Variabili di configurazione tramite .env |
| NFR-OPS-005 | Avvio in ordine corretto con dipendenze Docker (healthcheck gate) |

---

## 3. Requisiti Tecnici

### TR-STACK — Stack Tecnologico
| Componente | Tecnologia | Motivazione |
|------------|------------|-------------|
| Backend | FastAPI 0.116+ (Python 3.12) | Consistenza con IT_RESOURCE_MGMT, async nativo |
| Storage | openpyxl + master_cv.xlsx su SharePoint | Nessun DB separato, zero infrastruttura aggiuntiva |
| Frontend | React 18 + Vite 5 | Consistenza con IT_RESOURCE_MGMT, no Node.js locale |
| Auth locale | JWT HS256 + passlib pbkdf2 | Backdoor dev/emergenza |
| Auth SSO | Microsoft Entra ID (MSAL + Microsoft Graph) | Account aziendali esistenti |
| AI | OpenAI API (gpt-4o) | Qualità parsing, tool use per structured output |
| Export PDF | docxtpl + template DOCX | Template Jinja2 su SharePoint |
| Export JSON | json stdlib | Nativo Python |
| Containerizzazione | Docker + Docker Compose | 3 container: frontend, backend, ai-services |
| Reverse Proxy | Nginx (nel container frontend) | SPA routing + /api proxy |
| File Storage | SharePoint via Microsoft Graph API | CV e certificati in CER/ e CV/ |

### TR-DATA — Struttura Dati
| ID | Requisito |
|----|-----------|
| TR-DATA-001 | CV come insieme di tabelle relazionali (non JSONB puro) per queryability |
| TR-DATA-002 | Skill come tabella normalizzata con tassonomia (SkillTaxonomy) |
| TR-DATA-003 | Relazione User↔CV 1:1 (ogni utente ha un CV) |
| TR-DATA-004 | Upload files memorizzati su volume, path nel DB |
| TR-DATA-005 | Soft delete per utenti (campo `is_active`) |
| TR-DATA-006 | Timestamp `created_at`, `updated_at` su tutte le entità principali |
| TR-DATA-007 | Suggest-codes: source è `Certification.cert_code` (per-utente, non catalogo centrale) |

### TR-API — Design API
| ID | Requisito |
|----|-----------|
| TR-API-001 | Versioning API: prefisso `/api/v1/` |
| TR-API-002 | OpenAPI/Swagger auto-generato su `/docs` |
| TR-API-003 | Response model Pydantic su tutti gli endpoint |
| TR-API-004 | Errori standardizzati: `{"detail": "messaggio"}` |
| TR-API-005 | Upload multipart/form-data per documenti |
| TR-API-006 | Endpoint async per AI parsing (con polling status) |

---

## 4. Scope Sprint (alta priorità)

### Sprint 1 — Fondamenta ✅ (2026-03-14)
- Setup progetto, Docker Compose funzionante
- Backend: auth (login/logout), modello User, JWT
- Database: schema utenti + CV (struttura base)
- Frontend: login page, navigazione base, home page

### Sprint 2 — CV Base ✅ (2026-03-14)
- Backend: CRUD CV (anagrafica, skills, esperienze, formazione)
- Frontend: form CV utente (sezioni anagrafica + skill)
- Completeness score basic

### Sprint 3 — AI Parsing ✅ (2026-03-15)
- AI Service: endpoint parsing documento
- Backend: upload file, chiamata AI service, risposta strutturata
- Frontend: wizard upload → validazione dati estratti

### Sprint 4 — Sort + Export Prep + Hints ✅ (2026-03-16)
- Ordinamento referenze: end_date DESC NULLS FIRST + start_date DESC (sentinella "9999-99")
- Hint chips DB-driven: infrastruttura presente, disabilitata (riattivabile)
- Export DOCX: `docxtpl==0.19.0` in requirements.txt, `export.py` router registrato
- Password sync: `_sync_all_passwords` in lifespan per consistenza tutti gli utenti

### Sprint 5 — Cert Suggest + Refactoring ✅ (2026-03-17)
- Credly preview: anteprima badge da profilo Credly pubblico
- `POST /cv/cert-catalog/suggest-codes` — fuzzy match (Jaccard + SequenceMatcher ≥ 0.80) su cert utenti esistenti con codice
- Refactoring: eliminata tabella `cert_catalog` centralizzata; la fonte dei suggerimenti è ora la tabella `certifications` (per-utente, cert già presenti con codice valorizzato)
- Rimossi endpoint: `GET /cv/cert-catalog/search`, `POST /cv/cert-catalog/refresh`
- Eliminati: script `update_opentext_certs.py`, file `cert_catalog.json`, modello `CertCatalogEntry`

### Sprint 6 — SSO + People Analytics + Role Management (PIANIFICATO)

#### 6a — SSO Microsoft Entra ID
- Integrazione login con account Microsoft aziendale (MSAL flow)
- Token Entra ID validato dal backend (JWKS endpoint Azure)
- Mapping claim `preferred_username` / `email` → utente nel DB
- `AUTH_PROVIDER=entra` in `.env` per switch senza code change
- Fallback su auth locale se Entra non configurato

#### 6b — Role Management (ADMIN promuove altri ADMIN)
- Endpoint `PUT /users/{id}/role` — accessibile solo da ADMIN
- Frontend: nella lista utenti (tab Admin), dropdown ruolo con opzioni USER/ADMIN
- Audit: log della promozione (chi ha promosso chi, quando)

#### 6c — People Analytics (tile Admin)
- Nuovo tile "People Analytics" nella home Admin
- Ricerca/filtro multi-criterio: skill, livello, cert, lingua, disponibilità, BU, sede
- Tabella risultati con selezione multipla
- Export batch: Excel, PDF (zip), JSON strutturato per righe selezionate
- Dashboard: top skill, distribuzione livelli, completezza CV

#### 6d — Integrazione Allegati SharePoint
- Campo `sharepoint_url` su `Certification` e `Reference`
- Link cliccabile nel CV verso documento SharePoint
- (Futura) upload diretto via Microsoft Graph API

---

## 5. Out of Scope (v1)

- SSO / Microsoft Entra ID → **spostato in Sprint 6** (non più out of scope)
- Notifiche email (es. CV in scadenza)
- Mobile app
- S3 / storage cloud per upload
- Workflow di approvazione CV
- Import bulk utenti da Active Directory
- CV multi-lingua
- Integrazione con sistemi di recruiting esterni
- Upload diretto su SharePoint via Graph API (solo link per ora)
