# Piano Refactoring Production — CV Management

> Data: 2026-03-16 | Repo: https://github.com/COMPARG1976/cv-management

---

## Contesto

L'applicazione CV Management gira attualmente solo in DEV su questo PC.
Si vuole creare un'istanza PRD, inizialmente sullo stesso PC poi su EC2 AWS.

**Stato attuale problematico per la produzione:**
- `create_all()` + `seed_data()` + `seed_from_excel()` girano ad **ogni avvio** (guard idempotente ma rischioso)
- Nessuna differenziazione DEV/PRD (`APP_ENV`, `RUN_SEED`)
- Nessun sistema di migrazione DB (solo `ensure_schema_compatibility()` con raw SQL)
- Nessun backup automatico del DB
- Nessuno script di deploy
- Docker images non versionate
- `secret_key = "dev-secret-key-change-in-production"` hard-coded nel default

---

## Fasi del piano (in ordine di esecuzione)

---

### FASE 1 — Environment separation (basso rischio, immediata)

**File da modificare:**

`backend/app/database.py` — aggiungere a `Settings`:
```python
app_env: str = "development"          # development | production
run_seed: bool = True                 # False in PRD
run_seed_excel: bool = True           # False dopo prima inizializzazione PRD
```

`backend/app/main.py` — condizionare lifespan:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.app_env == "development":
        Base.metadata.create_all(bind=engine)   # solo in DEV
    ensure_schema_compatibility()
    os.makedirs(settings.upload_dir, exist_ok=True)
    if settings.run_seed:
        with SessionLocal() as db:
            seed_data(db)
    if settings.run_seed_excel:
        with SessionLocal() as db:
            seed_from_excel(db)
    yield
```

**Nuovi file da creare:**

`docker-compose.dev.yml` — override DEV (porta 8002, volumi locali, hot-reload):
```yaml
services:
  backend:
    environment:
      APP_ENV: development
      RUN_SEED: "true"
      RUN_SEED_EXCEL: "true"
```

`docker-compose.prd.yml` — override PRD:
```yaml
services:
  backend:
    restart: always
    environment:
      APP_ENV: production
      RUN_SEED: "false"
      RUN_SEED_EXCEL: "false"   # true solo al PRIMO avvio PRD
```

`.env.dev` — variabili DEV (già esistenti, riorganizzate)
`.env.prd` — variabili PRD con SECRET_KEY forte, password robuste, CORS PRD

**Comando DEV:**
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev up --build
```

**Comando PRD:**
```bash
docker compose -f docker-compose.yml -f docker-compose.prd.yml --env-file .env.prd up -d
```

---

### FASE 2 — Alembic (migrazioni DB versionabili)

**Razionale:** `create_all()` non gestisce ALTER TABLE. Alembic permette migrazioni forward/backward versionabili e sicure.

**Setup iniziale:**
```bash
cd backend
pip install alembic
alembic init alembic
```

**File da modificare dopo init:**

`backend/alembic.ini`:
```ini
sqlalchemy.url = %(DATABASE_URL)s   # letta da env, non hard-coded
```

`backend/alembic/env.py`:
```python
from app.database import engine
from app.models import Base
target_metadata = Base.metadata
# legge DATABASE_URL da env
```

**Prima migrazione — baseline schema attuale:**
```bash
alembic revision --autogenerate -m "baseline_sprint4"
alembic upgrade head   # in DEV per verificare
```

**Modifica main.py in PRD:**
```python
# In production: NON usare create_all(), lasciare ad Alembic
# L'upgrade head viene eseguito dallo script di deploy PRIMA di avviare il container
```

**Regola per future modifiche DB:**
- Ogni modifica a `models.py` → `alembic revision --autogenerate -m "descrizione"`
- Revisione manuale del migration file generato prima di applicare
- Cambi distruttivi (drop column, rename) → crea nuova colonna + script dati + depreca vecchia in fase successiva

**Script entrypoint backend** (`backend/entrypoint.sh`):
```bash
#!/bin/bash
set -e
if [ "$APP_ENV" = "production" ]; then
    echo "Running Alembic migrations..."
    alembic upgrade head
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

### FASE 3 — Backup DB

**Script** `scripts/backup_db.sh`:
```bash
#!/bin/bash
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups"
FILENAME="cv_management_${TIMESTAMP}.sql.gz"

docker exec cv_mgmt_db pg_dump \
  -U "${POSTGRES_USER:-cv_user}" \
  "${POSTGRES_DB:-cv_management}" \
  | gzip > "${BACKUP_DIR}/${FILENAME}"

echo "Backup: ${BACKUP_DIR}/${FILENAME}"

# Pulizia: mantieni ultimi 30 file
ls -t "${BACKUP_DIR}"/*.sql.gz | tail -n +31 | xargs -r rm
```

**Volume backup in docker-compose.prd.yml:**
```yaml
volumes:
  db_backups:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /opt/cv_management/backups
```

**Backup giornaliero** — container cron sidecar in `docker-compose.prd.yml`:
```yaml
  db-backup:
    image: postgres:15-alpine
    container_name: cv_mgmt_backup
    restart: always
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - db_backups:/backups
    environment:
      PGPASSWORD: "${POSTGRES_PASSWORD}"
    entrypoint: >
      sh -c "
        while true; do
          FILENAME=/backups/cv_$(date +%Y%m%d_%H%M%S).sql.gz
          pg_dump -h db -U $$POSTGRES_USER $$POSTGRES_DB | gzip > $$FILENAME
          echo Backup: $$FILENAME
          ls -t /backups/*.sql.gz | tail -n +31 | xargs -r rm
          sleep 86400
        done
      "
```

**Backup pre-deploy:** integrato nello script `deploy.sh` (vedi Fase 4).

**Futuro AWS:** sostituire destinazione locale con `aws s3 cp ... s3://bucket/backups/`

---

### FASE 4 — Script deploy locale → PRD

**`scripts/deploy.sh`** (deploy completo):
```bash
#!/bin/bash
set -e
ENV_FILE=".env.prd"
COMPOSE_PRD="-f docker-compose.yml -f docker-compose.prd.yml"
VERSION=$(date +%Y-%m-%d).$(git rev-parse --short HEAD)

echo "=== DEPLOY CV Management $VERSION ==="

# 1. Pull latest
git pull origin master

# 2. Pre-deploy backup DB
echo "--- Backup DB pre-deploy ---"
./scripts/backup_db.sh

# 3. Build immagini versionate
echo "--- Build immagini ---"
docker compose $COMPOSE_PRD --env-file $ENV_FILE build
docker tag 40cv_management-backend:latest 40cv_management-backend:$VERSION
docker tag 40cv_management-frontend:latest 40cv_management-frontend:$VERSION

# 4. Run Alembic migrations (container temporaneo, DB già attivo)
echo "--- Migrazione DB ---"
docker compose $COMPOSE_PRD --env-file $ENV_FILE run --rm backend \
  alembic upgrade head

# 5. Health check DB post-migrazione
echo "--- Health check DB ---"
docker exec cv_mgmt_db pg_isready -U cv_user || { echo "DB non pronto"; exit 1; }

# 6. Aggiorna container applicativi
echo "--- Aggiornamento container ---"
docker compose $COMPOSE_PRD --env-file $ENV_FILE up -d --no-deps backend frontend ai-services

# 7. Health check app
sleep 5
curl -sf http://localhost:8002/health || { echo "Backend health FAIL"; exit 1; }
echo "=== Deploy $VERSION completato ==="
```

**`scripts/init_prd.sh`** (SOLO prima inizializzazione PRD):
```bash
#!/bin/bash
# Da eseguire UNA SOLA VOLTA per inizializzare il DB PRD
# Poi impostare RUN_SEED_EXCEL=false in .env.prd

set -e
docker compose -f docker-compose.yml -f docker-compose.prd.yml \
  --env-file .env.prd \
  run --rm \
  -e RUN_SEED=true \
  -e RUN_SEED_EXCEL=true \
  backend python -c "
from app.database import SessionLocal, engine, Base
from app.models import *
from app.seed import seed_data
from app.seed_excel import seed_from_excel
Base.metadata.create_all(bind=engine)
with SessionLocal() as db:
    seed_data(db)
    seed_from_excel(db)
print('Init PRD completato')
"
```

---

### FASE 5 — Password initialization script

**`scripts/init_passwords.py`**:
```python
"""
Genera password temporanee per tutti gli utenti e le esporta in Excel.
Uso: python scripts/init_passwords.py --env .env.prd [--reset-all]
"""
import os, sys, secrets, string, argparse
from pathlib import Path
import pandas as pd

# Aggiunge backend al path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://cv_user:...")

from app.database import SessionLocal
from app.models import User
from app.security import hash_password

def generate_password(length=12):
    alphabet = string.ascii_letters + string.digits + "!@#$"
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        # almeno 1 maiuscola, 1 cifra, 1 speciale
        if (any(c.isupper() for c in pwd) and
            any(c.isdigit() for c in pwd) and
            any(c in "!@#$" for c in pwd)):
            return pwd

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset-all", action="store_true",
                        help="Resetta TUTTE le password, non solo quelle mai cambiate")
    args = parser.parse_args()

    rows = []
    with SessionLocal() as db:
        users = db.query(User).filter(User.is_active == True).all()
        for user in users:
            new_pwd = generate_password()
            user.password_hash = hash_password(new_pwd)
            rows.append({
                "Nome":      user.full_name,
                "Email":     user.email,
                "Password":  new_pwd,
                "Ruolo":     user.role.value,
            })
        db.commit()

    df = pd.DataFrame(rows)
    out = f"passwords_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.xlsx"
    df.to_excel(out, index=False)
    print(f"Password generate: {len(rows)} utenti → {out}")
    print("ATTENZIONE: distribuisci il file e poi CANCELLALO dal PC.")

if __name__ == "__main__":
    main()
```

**Output:** `passwords_YYYYMMDD_HHMM.xlsx` con colonne Nome | Email | Password | Ruolo.
> Il file NON va mai committato su GitHub (aggiungere `passwords_*.xlsx` a `.gitignore`).

---

### FASE 6 — AWS EC2 (seconda fase, dopo validazione locale)

**Architettura target:**

```
Internet → ALB (443) → EC2 (t3.medium)
                          ├── container: frontend (Nginx :80)
                          ├── container: backend (:8000)
                          ├── container: ai-services (:8000)
                          └── RDS PostgreSQL (db.t3.micro, Multi-AZ opz.)

S3 bucket: cv-management-backups/
ECR: repository immagini Docker versionate
```

**docker-compose.aws.yml** — override per AWS:
```yaml
services:
  db:
    # rimosso: usa RDS esterno
    deploy: { replicas: 0 }
  backend:
    environment:
      DATABASE_URL: "postgresql+psycopg2://cv_user:PWD@rds-endpoint:5432/cv_management"
  ai-services:
    environment:
      OPENAI_API_KEY: "${OPENAI_API_KEY}"
```

**Script deploy EC2** (`scripts/deploy_aws.sh`):
```bash
# 1. Push immagini su ECR
aws ecr get-login-password | docker login --username AWS --password-stdin $ECR_REGISTRY
docker tag backend:$VERSION $ECR_REGISTRY/cv-backend:$VERSION
docker push $ECR_REGISTRY/cv-backend:$VERSION

# 2. SSH su EC2 e deploy
ssh ec2-user@$EC2_HOST "cd /opt/cv_management && ./scripts/deploy.sh"
```

**Backup su S3** (aggiunta in backup_db.sh):
```bash
aws s3 cp "${BACKUP_DIR}/${FILENAME}" "s3://cv-management-backups/${FILENAME}"
```

---

### FASE 7 — Rollback strategy

**Scenario:** deploy fallisce DOPO che Alembic ha già migrato il DB.

**Regola per migrazioni forward-compatible:**
- Mai DROP COLUMN direttamente → depreca prima, rimuovi dopo 2 sprint
- Nuove colonne sempre con DEFAULT o NULLABLE
- Rename: aggiungi nuova colonna → copia dati → depreca vecchia

**Script rollback** (`scripts/rollback.sh`):
```bash
#!/bin/bash
# Rollback rapido: ripristina immagini versione precedente
PREV_VERSION=$1
docker compose $COMPOSE_PRD up -d --no-deps \
  --image 40cv_management-backend:$PREV_VERSION \
  backend

# Se necessario rollback DB (solo se migration era reversible):
# docker compose run --rm backend alembic downgrade -1
```

---

## File da creare (riepilogo)

| File | Fase | Scopo |
|------|------|-------|
| `docker-compose.dev.yml` | 1 | Override DEV |
| `docker-compose.prd.yml` | 1 | Override PRD |
| `docker-compose.aws.yml` | 6 | Override AWS |
| `.env.dev` | 1 | Variabili DEV |
| `.env.prd` | 1 | Variabili PRD (non committato) |
| `backend/entrypoint.sh` | 2 | Alembic upgrade + uvicorn |
| `backend/alembic/` | 2 | Migration system |
| `scripts/backup_db.sh` | 3 | Backup manuale pg_dump (pre-deploy) |
| `scripts/deploy.sh` | 4 | Deploy pipeline locale |
| `scripts/init_prd.sh` | 4 | Init one-time PRD |
| `scripts/deploy_aws.sh` | 6 | Deploy pipeline AWS |
| `scripts/rollback.sh` | 4/6 | Rollback container |
| `scripts/init_passwords.py` | 5 | Genera Excel password |

## File da modificare

| File | Fase | Modifica |
|------|------|---------|
| `backend/app/database.py` | 1 | + `app_env`, `run_seed`, `run_seed_excel` |
| `backend/app/main.py` | 1+2 | lifespan condizionale |
| `backend/Dockerfile` | 2 | ENTRYPOINT → entrypoint.sh |
| `backend/requirements.txt` | 2 | + alembic |
| `.gitignore` | 5 | + `passwords_*.xlsx`, `.env.prd` |

---

## Ordine di esecuzione consigliato

1. **Fase 1** — Environment separation (non rompe nulla, sicura)
2. **Fase 5** — Password init script (indipendente, serve subito)
3. **Fase 2** — Alembic (richiede test in DEV prima di PRD)
4. **Fase 3** — Backup script
5. **Fase 4** — Deploy script (unifica tutto)
6. **Fase 6** — AWS (dopo validazione locale completa)

---

## Verifica end-to-end

```bash
# 1. DEV continua a funzionare
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
curl http://localhost:8002/health

# 2. PRD prima inizializzazione
./scripts/init_prd.sh
./scripts/deploy.sh

# 3. Test migrazione Alembic
alembic upgrade head   # deve completare senza errori
alembic current        # deve mostrare revision corrente
alembic history        # deve mostrare baseline_sprint4

# 4. Test backup
./scripts/backup_db.sh
ls -la /backups/*.sql.gz

# 5. Test password init
python scripts/init_passwords.py --env .env.prd
# verifica che passwords_YYYYMMDD.xlsx contenga tutti gli utenti
```
