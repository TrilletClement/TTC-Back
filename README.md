# TTC-Back

FastAPI + PostgreSQL backend for STIB transit LED board management and ordering.
The Angular frontend lives in the sibling repo **TTC-Front** (clone it next to this one:
`~/projets/TTC-Back` and `~/projets/TTC-Front`).

## Table of Contents

1. [Quick start (nouveau collaborateur)](#quick-start-nouveau-collaborateur)
2. [Architecture](#architecture)
3. [Environment Setup](#environment-setup)
4. [Local Development (PM2)](#local-development-pm2)
5. [Production Deployment (Docker)](#production-deployment-docker)
6. [Database Migrations (Alembic)](#database-migrations-alembic)
7. [Reference](#reference)

---

## Quick start (nouveau collaborateur)

Objectif : API sur http://localhost:8000 et site sur http://localhost:4200.
Les deux repos se clonent **côte à côte** :

```bash
mkdir -p ~/projets && cd ~/projets
git clone git@github.com:TrilletClement/TTC-Back.git
git clone git@github.com:TrilletClement/TTC-Front.git
```

**Outils requis** : Git, Docker (+ Compose), Python 3.10+ (3.11 en prod/Docker),
Node.js 20+ (22 dans le Dockerfile du front). Sous Debian/Ubuntu :
`sudo apt install python3-venv libpq-dev python3-dev build-essential libcairo2 fontconfig`
(cairo/fontconfig : rendu PNG des lignes pour l'app Android).

### 1. Backend

```bash
cd ~/projets/TTC-Back
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env     # puis éditer, voir « Environment Setup »
```

### 2. Base de données

Le plus simple : le service `db` du compose (PostgreSQL 15, publié sur le port **5434**,
identifiants = `POSTGRES_*` du `.env`) :

```bash
docker compose up -d db
# dans .env : DB_PORT=5434
```

(Alternative : un PostgreSQL local sur 5432 — voir « Local Development (PM2) ».)

**Base vide** — les migrations Alembic ne se rejouent *pas* depuis zéro (les premières
supposent des tables existantes). On crée le schéma depuis les modèles, puis on
marque la base comme à jour :

```bash
PYTHONPATH=. python scripts/create_all_tables.py
PYTHONPATH=. python -m alembic stamp head
```

**Base existante** (dump de prod, etc.) : `python -m alembic upgrade head`.

### 3. Données de transport (optionnel mais nécessaire pour voir des lignes)

```bash
PYTHONPATH=. python -m app.routines.stib_import     # STIB (clé STIB_API_KEY requise)
PYTHONPATH=. python -m app.routines.tec_import      # TEC — peut être long
```

De Lijn / SNCB : `delijn_import`, `sncb_import`.

### 4. Lancer l'API et le scheduler

```bash
PYTHONPATH=. uvicorn app.main:app --reload --port 8000     # terminal 1
PYTHONPATH=. python -m app.routines.scheduler              # terminal 2 (temps réel, matview…)
```

Vérification : `curl localhost:8000/` → `{"message":"API is running"}`.
Tests : `PYTHONPATH=. python -m pytest tests` (sans base de données).

### 5. Frontend

```bash
cd ~/projets/TTC-Front
npm install
npm start                # http://localhost:4200, /api proxifié vers localhost:8000
```

Voir le README de TTC-Front. Pour tout lancer d'un coup avec PM2 : « Local Development (PM2) ».

---

## Architecture

```
TTC-Back/
├── app/
│   ├── core/config.py         # Pydantic settings — lit .env à la racine du repo
│   ├── routers/
│   ├── services/
│   ├── orm_models/
│   └── routines/              # scheduler + imports GTFS
├── migrations/                # Alembic migration files
├── scripts/                   # create_all_tables, backup DB, …
├── Dockerfile                 # image stib-api:latest (api + scheduler)
├── .env                       # gitignored — copy from .env.example
├── .env.example               # committed template with all variable names
├── ecosystem.local.config.js  # PM2 local dev config (starts ../TTC-Front too)
├── ecosystem.config.js        # PM2 production config
├── docker-compose.yml         # Docker production config (shared with TTC-Front)
└── deploy.sh                  # Production deployment (API image, DB, migrations)
```

**PM2 services (local dev):**

| Name              | What it runs                              | URL                    |
|-------------------|-------------------------------------------|------------------------|
| `stib-frontend`   | Angular dev server (from `../TTC-Front`)  | http://localhost:4200  |
| `stib-api`        | FastAPI + uvicorn --reload                | http://localhost:8000  |
| `stib-scheduler`  | Background import/sync scheduler          | —                      |
| `stib-stripe`     | Stripe CLI webhook tunnel (local testing) | —                      |

**Docker services (production):**

| Service     | Port  | Description              |
|-------------|-------|--------------------------|
| `db`        | 5434  | PostgreSQL 15            |
| `api`       | 8000  | FastAPI + Uvicorn        |
| `scheduler` | —     | Background task runner   |
| `frontend`  | 4200  | Angular served by Nginx (image shipped by TTC-Front) |

---

## Environment Setup

**All configuration lives in a single `.env` at the repo root.** It is gitignored — never commit it.

```bash
cp .env.example .env
```

Variables **obligatoires** (l'API refuse de démarrer sans elles — des valeurs bidon
conviennent en local) : `JWT_SECRET_KEY` (≥ 32 caractères), `DEPLOY_SECRET`,
`STIB_API_KEY`, `TURNSTILE_SECRET_KEY`, `MAIL_USERNAME`, `MAIL_PASSWORD`,
`MAIL_FROM`, `MAIL_SERVER`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`,
`FRONTEND_URL`. Les autres (Google, SendCloud, OpenAI, TEC…) sont optionnelles ;
les fonctionnalités correspondantes sont simplement désactivées si vides.
`DATABASE_URL` n'existe pas : elle est dérivée de `POSTGRES_*`, `DB_HOST` et `DB_PORT`.

| Variable               | Local dev value            | Production value                    |
|------------------------|----------------------------|-------------------------------------|
| `FRONTEND_URL`         | `http://localhost:4200`    | `https://transport.trillet.be`      |
| `API_BASE_URL`         | `http://localhost:8000`    | `https://transport.trillet.be`      |
| `DB_PORT`              | `5434` (compose) ou `5432` (PostgreSQL local) | fixé à 5432 par docker-compose |
| `FIRMWARE_DIR` / `BLOG_EMBEDS_DIR` | `./data/...` (dossiers locaux) | `/data/firmware`, `/data/blog-embeds` (volumes Docker) |
| `STRIPE_SECRET_KEY`    | `sk_test_...`              | `sk_live_...` (when going live)     |
| `STRIPE_WEBHOOK_SECRET`| from `stripe listen` output| from Stripe dashboard               |

`FRONTEND_URL` controls Stripe redirect URLs and auth email links.
`API_BASE_URL` is injected into `../TTC-Front/public/runtime-env.js` by the PM2 local config
(set `FRONT_DIR` to use another location). Avec `npm start` dans TTC-Front, ce n'est pas
nécessaire (le proxy gère `/api`).

---

## Local Development (PM2)

PM2 démarre front + API + scheduler + Stripe CLI d'un coup. Prérequis supplémentaires :

```bash
sudo npm install -g pm2
# Stripe CLI (test des paiements en local)
curl -s https://packages.stripe.dev/api/security/keypair/stripe-cli-gpg/public \
  | gpg --dearmor | sudo tee /usr/share/keyrings/stripe.gpg > /dev/null
echo "deb [signed-by=/usr/share/keyrings/stripe.gpg] https://packages.stripe.dev/stripe-cli-debian-local stable main" \
  | sudo tee /etc/apt/sources.list.d/stripe.list
sudo apt update && sudo apt install stripe
# Frontend deps (repo frère)
cd ../TTC-Front && npm install && cd ../TTC-Back
```

### First-time setup

```bash
# 1. Python environment (see Quick start)
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 2. PostgreSQL local sur 5432 (ou `docker compose up -d db` + DB_PORT=5434 dans .env)
sudo service postgresql start
sudo -u postgres psql -c "CREATE USER mylocaldb WITH PASSWORD 'mylocaldb';"
sudo -u postgres psql -c "CREATE DATABASE mylocaldb OWNER mylocaldb;"

# 3. Schema — base vide : create_all + stamp (les migrations ne se rejouent pas depuis zéro)
PYTHONPATH=. python scripts/create_all_tables.py && python -m alembic stamp head
#    base existante : python -m alembic upgrade head

# 4. Stripe CLI — authenticate once (opens browser)
stripe login
```

### Start all services

```bash
pm2 start ecosystem.local.config.js
pm2 save
```

This also auto-generates `../TTC-Front/public/runtime-env.js` from `API_BASE_URL` in `.env`.

### First-time Stripe webhook secret

On the first start, get the webhook signing secret from the CLI output:

```bash
pm2 logs stib-stripe --lines 20
# Look for: "Your webhook signing secret is whsec_..."
```

Copy the `whsec_...` value into `.env` as `STRIPE_WEBHOOK_SECRET`, then:

```bash
pm2 restart stib-api
```

The secret is stable for your Stripe account + machine — you only do this once.

### Resending a missed webhook event

If a payment went through but the order status didn't update, resend the event:

```bash
# Find the event ID in your Stripe dashboard → Developers → Events
stripe events resend evt_xxxx
```

---

## Production Deployment (Docker)

### First-time server setup

SSH into the production server and create the prod `.env`:

```bash
cp .env.example .env
# Set production values:
#   FRONTEND_URL=https://transport.trillet.be
#   API_BASE_URL=https://transport.trillet.be
#   POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB (DB_HOST/DB_PORT are set by docker-compose)
#   FIRMWARE_DIR=/data/firmware  BLOG_EMBEDS_DIR=/data/blog-embeds   (volumes mounted by compose)
#   STRIPE_SECRET_KEY=sk_live_...     (when going live)
#   STRIPE_WEBHOOK_SECRET=whsec_...   (from Stripe dashboard → Webhooks)
#   ... all other production secrets
```

The production server's `.env` is never transferred by `deploy.sh` — it is managed directly on the server.

### Build and deploy

```bash
# Deploy the API (builds stib-api:latest itself)
./deploy.sh

# Frontend: see TTC-Front (its own ./deploy.sh). On a compose/runtime-env change,
# deploy TTC-Back first — it ships docker-compose.yml and /root/frontend/runtime-env.js.
```

**What `deploy.sh` does:**

1. Builds the API image and saves it as a gzip tarball
2. Transfers the image + `docker-compose.yml` to the server via SCP
3. On server: reads `API_BASE_URL` from `/root/.env` → writes `/root/frontend/runtime-env.js`
4. Loads the image, runs `docker compose up -d`
5. Waits for DB readiness, runs `alembic upgrade head`
6. Cleans up tarballs and dangling images

### Docker commands

```bash
docker compose ps
docker compose logs -f api
docker compose up -d --build api    # rebuild and restart only the API (local)
docker compose down                  # stop containers, keep DB volume
docker compose down -v               # stop containers AND delete DB volume (full reset)
docker compose exec db psql -U mylocaldb -d mylocaldb
```

---

## Database Migrations (Alembic)

All Alembic commands run inside the `api` container in production, or directly with the venv activated locally.

**Local:**
```bash
source venv/bin/activate
python -m alembic upgrade head
python -m alembic current
python -m alembic history
```

**Docker (production):**
```bash
docker compose exec api sh -c "cd /app && python -m alembic <command>"
```

### Create a new migration

```bash
# After modifying SQLAlchemy models:
python -m alembic revision --autogenerate -m "describe your change"
# Review the generated file in migrations/versions/
python -m alembic upgrade head
```

### Fresh database (first-time)

```bash
# Start the stack, then create the schema from the models (the API does NOT do it on startup)
docker compose up -d --build
docker compose exec api sh -c "cd /app && python scripts/create_all_tables.py"

# Stamp Alembic at head so future migrations work cleanly
docker compose exec api sh -c "cd /app && python -m alembic stamp head"
```

### Existing database (tables exist, no alembic_version)

Use this when the DB was built from raw SQL scripts without Alembic involvement:

```bash
# 1. Find the last revision whose SQL was already applied
docker compose exec api sh -c "cd /app && python -m alembic history --verbose"

# 2. Stamp at that revision (creates alembic_version table, touches nothing else)
docker compose exec api sh -c "cd /app && python -m alembic stamp <last_applied_revision>"

# 3. Apply only the missing migrations
docker compose exec api sh -c "cd /app && python -m alembic upgrade head"

# 4. Verify
docker compose exec api sh -c "cd /app && python -m alembic current"
```

---

## Reference

### PM2 commands

```bash
pm2 status                        # all process statuses
pm2 logs [service]                # live log tail
pm2 logs stib-api --lines 50      # last N lines
pm2 restart [service|all]
pm2 stop all
pm2 delete all
pm2 save                          # persist process list across reboots
pm2 startup                       # configure PM2 to start on boot
```

### GitHub SSH setup (new machine)

```bash
ssh-keygen -t ed25519 -C "your.email@example.com"
eval "$(ssh-agent -s)" && ssh-add ~/.ssh/id_ed25519
cat ~/.ssh/id_ed25519.pub         # paste into GitHub → Settings → SSH keys
ssh -T git@github.com             # verify
git clone git@github.com:TrilletClement/TTC-Back.git
git clone git@github.com:TrilletClement/TTC-Front.git
```

### Troubleshooting

**API won't start — pydantic validation error:**
Check that all required variables in `.env` are set. Compare against `.env.example`.

**Stripe webhook not updating order status:**
1. Check `pm2 logs stib-stripe` — tunnel must show events being forwarded with `[200]`
2. Check `pm2 logs stib-api` — look for errors around the webhook call
3. If the event returned 500, fix the issue and resend: `stripe events resend evt_xxx`

**`DetachedInstanceError` in SQLAlchemy:**
A lazy-loaded relationship is accessed outside its session. Add `.options(joinedload(...))` to the query or move attribute access inside the session scope.

**Angular CLI requires newer Node.js:**
```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

**psycopg2 build error:**
```bash
sudo apt install libpq-dev python3-dev build-essential
pip install psycopg2-binary
```

**Docker port 5434 conflict:**
Edit `docker-compose.yml` and change `"5434:5432"` to a free port.
