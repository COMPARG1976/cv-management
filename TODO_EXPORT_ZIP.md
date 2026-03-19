# TODO — Export selettivo CV e Certificazioni via ZIP

> Stato: **DA FARE** — concetto approvato, non ancora implementato.
> Prerequisito: completare la migrazione naming/cartelle SP (tipo-first: `CV/` e `CER/`).

---

## Obiettivo

Permettere all'amministratore di selezionare un sottoinsieme di persone/certificazioni
e ricevere due archivi ZIP scaricabili:
- `export_CV_<data>.zip`   — CV delle persone selezionate
- `export_CER_<data>.zip`  — certificazioni selezionate

Senza bloccare l'applicazione e senza modifiche al codice dell'app.

---

## Flusso operativo

```
1. Admin copia master_cv.xlsx in locale
   (non tocca il file su SharePoint → utenti non bloccati)

2. Apre il file in Excel e lavora su due sheet:

   Sheet "Staff" → colonna "export" (ultima colonna)
     X = includi il CV di questa persona nello zip CV

   Sheet "Certifications" → colonna "export" (ultima colonna)
     X = includi questo allegato nello zip CER

3. Salva il file con le X e lo passa allo script

4. Lo script:
   a. Legge il file Excel marcato
   b. Per ogni persona con export=X in Staff:
        → cerca su SP in CV/   i file che matchano {email_prefix}_CV_*
        → scarica e aggiunge a export_CV.zip
   c. Per ogni cert con export=X in Certifications:
        → legge sharepoint_path dalla riga
        → scarica da SP il file
        → aggiunge a export_CER.zip
   d. Salva i due ZIP in locale

5. Admin scarica i due ZIP
```

---

## Struttura ZIP output

```
export_CV_20260320/
  mario.rossi_CV_CurriculumVi.pdf
  luigi.verdi_CV_CV2024aggior.pdf
  anna.bianchi_CV_Curriculum.pdf

export_CER_20260320/
  mario.rossi_CER_5-0155_SAPFound.pdf
  mario.rossi_CER__AWSArchitec.pdf
  luigi.verdi_CER_AZ900_AzureFund.pdf
```

Flat all'interno degli ZIP (nessuna sottocartella) — il naming convention
`{prefix}_{tipo}_{...}` è già sufficiente per capire a chi appartiene ogni file.

Opzione alternativa (configurabile via flag `--by-person`):
```
export_CV_20260320/
  mario.rossi/
    mario.rossi_CV_CurriculumVi.pdf
  luigi.verdi/
    ...
```

---

## Dettagli tecnici dello script

### File: `scripts/export_zip.py`

```
Dipendenze standalone (no Docker necessario):
  - openpyxl           (legge Excel marcato)
  - httpx              (download da SharePoint via Graph API)
  - python-dotenv      (legge .env per credenziali SP)
  - zipfile            (stdlib)

Credenziali SP da .env:
  ENTRA_TENANT_ID, ENTRA_CLIENT_ID, ENTRA_CLIENT_SECRET
  SHAREPOINT_SITE_URL, SHAREPOINT_DRIVE_NAME, SHAREPOINT_ROOT_FOLDER
```

### Argomenti CLI
```bash
python scripts/export_zip.py \
  --input master_cv_marked.xlsx \
  --output ./export_20260320 \
  [--cv]           # genera solo ZIP cv
  [--cer]          # genera solo ZIP cert
  [--by-person]    # organizza ZIP con sottocartelle per persona
  [--dry-run]      # stampa cosa farebbe senza scaricare
```

### Logica di ricerca file CV su SharePoint
Dato `email = mario.rossi@mashfrog.com`:
- `email_prefix = "mario.rossi"`
- Lista file in `CV/` su SP (una sola chiamata Graph `/children`)
- Filtra: `name.startswith("mario.rossi_CV_")`
- Prende il file più recente se ce ne sono più versioni
  (o tutti, configurabile con flag `--all-versions`)

### Logica per certificazioni
Dato una riga Certifications con `sharepoint_path` valorizzato:
- Se `doc_attachment_type = SHAREPOINT`: scarica direttamente da `sharepoint_path`
- Se `doc_attachment_type = URL`: scarica da `doc_url` (link esterno)
- Se `doc_attachment_type = NONE` o path vuoto: skip con warning nel log

### Report finale
```
=== Export completato ===
CV:            23 file scaricati, 2 non trovati su SP (warning)
Certificazioni: 47 file scaricati, 5 senza allegato (skip)

File non trovati:
  - anna.bianchi: nessun CV in CV/ su SharePoint
  - luca.neri: nessun CV in CV/ su SharePoint

Output:
  ./export_20260320/export_CV_20260320.zip   (23 file, 18.4 MB)
  ./export_20260320/export_CER_20260320.zip  (47 file, 62.1 MB)
```

---

## Prerequisiti da completare prima

1. **Migrazione struttura cartelle SP** — passare da `{email}/CV/` a tipo-first `CV/` e `CER/`
2. **Naming convention** — implementare `_build_sp_filename()` nell'upload router
3. **Script import certificazioni** — (vedi ragionamento separato) per pre-caricare
   l'archivio esistente con i path SP già in formato `CER/{prefix}_CER_{code}_{base}.pdf`

---

## Note aggiuntive

- La colonna `export` nel file marcato NON viene mai persistita su master_cv.xlsx originale:
  lo script lavora su una COPIA locale, il file su SP rimane invariato.
- Se in futuro si vuole un export direttamente dall'UI, questo script è la base:
  basta aggiungere un endpoint `POST /export/zip` che esegue la stessa logica
  e restituisce uno `StreamingResponse` con il file ZIP.
- Considerare un flag `--since YYYY-MM-DD` per filtrare solo certificazioni
  acquisite dopo una certa data (utile per audit periodici).
