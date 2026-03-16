# TODO — Sprint 5  (CV Management)

> Creato: 2026-03-16
> Repo: https://github.com/COMPARG1976/cv-management

---

## COMPLETATO in Sprint 5

### ✅ Cert Catalog — Modello e populate
- Modello `CertCatalogEntry` (`cert_catalog`): `name`, `vendor`, `cert_code`, `img_url`, `credly_id`, `updated_at`
- `populate_cert_catalog(db)` in lifespan — upsert idempotente su `credly_id` o `(name, vendor)`
- Script `_build_cert_catalog.py`: SAP (113) + OpenText (227) + Databricks (10) → `cert_catalog.json`
- DB caricato: ~2168 entry totali

### ✅ Cert Catalog — API
- `GET /cv/cert-catalog/search?q=&vendor=&limit=10` — autocomplete ILIKE con ranking
- `POST /cv/cert-catalog/suggest-codes` — fuzzy match SequenceMatcher ≥ 0.80
- `POST /cv/cert-catalog/refresh` — re-fetch fonti + aggiorna JSON + DB

### ✅ Frontend cert UX
- `AutocompleteInput` su campo "Nome certificazione" — dropdown con img + vendor + codice
- On-select: pre-popola `cert_code`, `issuing_org`, `badge_image_url`
- `useEffect` su `cv.certifications` → `suggestCertCodes` → hint chips per cert senza codice
- Hint chip: solo se `sug.cert_code && !c.cert_code` — mostra "Codice esame: X_XXXX · Vendor"
- Credly preview: badge arricchito con `cert_code` da catalogo via `credly_id`

### ✅ Password sync
- `_sync_all_passwords(db)` chiamato in lifespan dopo seed_data + seed_from_excel
- Garantisce consistenza per TUTTI gli utenti (seed + Excel) ad ogni avvio

---

## PRIORITA' ALTA

### 1. Export DOCX — Feature principale

Implementare export CV in formato Word tramite `docxtpl` (gia' aggiunto a requirements.txt).
Router `export.py` gia' registrato in `main.py` con prefisso `/export`.

**Backend (`backend/app/routers/export.py`)**
```
GET /export/cv/docx?template=standard
```
- Carica CV dell'utente autenticato (stesso query di get_my_cv)
- Carica template da `backend/app/templates/docx/cv_{template}.docx`
- Inietta contesto con tutti i campi (vedi nomi corretti sotto)
- Restituisce `StreamingResponse` con `Content-Disposition: attachment`

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

## PRIORITA' MEDIA

### 2. Admin UI — Trigger refresh catalogo certificazioni

Endpoint `POST /cv/cert-catalog/refresh` esiste ma:
- Accessibile a qualsiasi utente autenticato (nessun check ruolo)
- Nessuna UI nel pannello admin

**Azioni:**
1. Aggiungere guard `require_roles(UserRole.ADMIN)` sull'endpoint `/refresh`
2. Aggiungere pulsante "Aggiorna Catalogo Certificazioni" nel pannello Admin
3. Mostrare: ultimo aggiornamento, numero entry per vendor

### 3. Admin UI — Reset password utente

`FR-ADMIN-005` e `FR-ADMIN-006` — attualmente nessuna UI admin per reset password.

Opzioni:
- Pulsante "Reset Password" nella lista utenti admin → genera temp password → mostra a schermo
- Oppure: integrazione con `scripts/init_passwords.py` per export Excel

### 4. Pulizia codice hints (opzionale)

Il codice hints e' **disabilitato ma presente**. Decidere se:
- Tenerlo commentato (riattivabile in futuro)
- Rimuoverlo completamente per ridurre complessita'

File coinvolti:
- `frontend/src/App.jsx`: `HintChip` component, `hints` state in MyCVView, prop `hints={}` su tutti i tab
- `frontend/src/api.js`: `getCVHints`
- `backend/app/routers/cv.py`: `GET /me/hints` endpoint
- `ai-services/app/suggester.py`: file non usato (era per AI suggestions)
- `ai-services/app/main.py`: `POST /suggest` endpoint non usato

### 5. Fix record orfano esperienze

Verificare/eliminare record `id=15` (company Mashfrog, `cv_id=11`) che risultava orfano.
```bash
docker exec cv_db psql -U cv_user -d cv_management \
  -c "SELECT id, cv_id, company_name, role FROM \"references\" WHERE id=15;"
```

### 6. Tab Esperienze — verifica filtri frontend

Controllare che il tab Esperienze mostri TUTTI i record del DB senza filtri nascosti in App.jsx.

### 7. UX Diff wizard Step 3

Badge `db_only` nelle esperienze: aggiungere testo esplicativo
"Gia' presente nel tuo profilo — gestiscilo dalla tab Esperienze"

---

## NOTE TECNICHE

- `docxtpl==0.19.0` aggiunto a `backend/requirements.txt` — rebuild backend richiesto
- Template DOCX va incluso nel Docker image (Dockerfile copia `app/` → `app/templates/` inclusa)
- docxtpl usa python-docx internamente; non e' necessario installare python-docx separatamente
- Per blocchi multi-paragrafo: usare `{%p for %}` / `{%p endfor %}` (non `{%tr %}` che e' per tabelle)
- `cert_catalog.json` (62 KB) e' incluso nel Docker image tramite COPY in Dockerfile
- `_build_cert_catalog.py` va eseguito localmente con `python _build_cert_catalog.py` per aggiornare il JSON prima del rebuild
- Aggiungere `passwords_*.xlsx` a `.gitignore` prima di generare password PRD
