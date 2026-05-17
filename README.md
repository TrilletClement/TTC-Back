# Server STIB

Angular + FastAPI + PostgreSQL application for STIB transit LED board management and ordering.

## Table of Contents

1. [Architecture](#architecture)
2. [Prerequisites](#prerequisites)
3. [Environment Setup](#environment-setup)
4. [Local Development (PM2)](#local-development-pm2)
5. [Production Deployment (Docker)](#production-deployment-docker)
6. [Database Migrations (Alembic)](#database-migrations-alembic)
7. [Reference](#reference)

---

## Architecture

```
server-STIB/
├── fastapi-server/            # FastAPI backend + scheduler
│   ├── app/
│   │   ├── core/config.py     # Pydantic settings — reads root .env
│   │   ├── routers/
│   │   ├── services/
│   │   └── orm_models/
│   └── migrations/            # Alembic migration files
├── stibFront/                 # Angular frontend
│   ├── public/runtime-env.js  # auto-generated (gitignored)
│   └── Dockerfile
├── .env                       # gitignored — copy from .env.example
├── .env.example               # committed template with all variable names
├── ecosystem.local.config.js  # PM2 local dev config (gitignored)
├── ecosystem.config.js        # PM2 production config
├── docker-compose.yml         # Docker production config
└── deploy.sh                  # Production deployment script
```

**PM2 services (local dev):**

| Name              | What it runs                              | URL                    |
|-------------------|-------------------------------------------|------------------------|
| `stib-frontend`   | Angular dev server                        | http://localhost:4200  |
| `stib-api`        | FastAPI + uvicorn --reload                | http://localhost:8000  |
| `stib-scheduler`  | Background import/sync scheduler          | —                      |
| `stib-stripe`     | Stripe CLI webhook tunnel (local testing) | —                      |

**Docker services (production):**

| Service     | Port  | Description              |
|-------------|-------|--------------------------|
| `db`        | 5434  | PostgreSQL 15            |
| `api`       | 8000  | FastAPI + Uvicorn        |
| `scheduler` | —     | Background task runner   |
| `frontend`  | 4200  | Angular served by Nginx  |

---

## Prerequisites

```bash
# Node.js 20+ (use NodeSource)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# PM2
sudo npm install -g pm2

# Angular CLI
cd stibFront && sudo npm install && sudo npm install -g @angular/cli && cd ..

# Python 3.10+ venv + build tools
sudo apt install python3.10-venv libpq-dev python3-dev build-essential -y

# Stripe CLI (for local payment testing)
curl -s https://packages.stripe.dev/api/security/keypair/stripe-cli-gpg/public \
  | gpg --dearmor | sudo tee /usr/share/keyrings/stripe.gpg > /dev/null
echo "deb [signed-by=/usr/share/keyrings/stripe.gpg] https://packages.stripe.dev/stripe-cli-debian-local stable main" \
  | sudo tee /etc/apt/sources.list.d/stripe.list
sudo apt update && sudo apt install stripe
```

---

## Environment Setup

**All configuration lives in a single `.env` at the project root.** It is gitignored — never commit it.

```bash
cp .env.example .env
# Edit .env and fill in real values (see comments inside)
```

Key variables to set:

| Variable               | Local dev value            | Production value                    |
|------------------------|----------------------------|-------------------------------------|
| `FRONTEND_URL`         | `http://localhost:4200`    | `https://transport.trillet.be`      |
| `API_BASE_URL`         | `http://localhost:8000`    | `https://transport.trillet.be`      |
| `DATABASE_URL`         | local PostgreSQL URL       | built by docker-compose from POSTGRES_* |
| `STRIPE_SECRET_KEY`    | `sk_test_...`              | `sk_live_...` (when going live)     |
| `STRIPE_WEBHOOK_SECRET`| from `stripe listen` output| from Stripe dashboard               |

`FRONTEND_URL` controls Stripe redirect URLs and auth email links.  
`API_BASE_URL` is injected into `stibFront/public/runtime-env.js` automatically at PM2 startup.

---

## Local Development (PM2)

### First-time setup

```bash
# 1. Python environment
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r fastapi-server/requirements.txt

# 2. Local PostgreSQL (if not already running)
sudo service postgresql start
sudo -u postgres psql -c "CREATE USER mylocaldb WITH PASSWORD 'mylocaldb';"
sudo -u postgres psql -c "CREATE DATABASE mylocaldb OWNER mylocaldb;"

# 3. Run migrations
cd fastapi-server && python -m alembic upgrade head && cd ..

# 4. Stripe CLI — authenticate once (opens browser)
stripe login
```

### Start all services

```bash
pm2 start ecosystem.local.config.js
pm2 save
```

This also auto-generates `stibFront/public/runtime-env.js` from `API_BASE_URL` in `.env`.

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
#   DATABASE_URL=postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
#   STRIPE_SECRET_KEY=sk_live_...     (when going live)
#   STRIPE_WEBHOOK_SECRET=whsec_...   (from Stripe dashboard → Webhooks)
#   ... all other production secrets
```

The production server's `.env` is never transferred by `deploy.sh` — it is managed directly on the server.

### Build and deploy

```bash
# Build Docker images locally
docker build -t stib-api:latest ./fastapi-server
docker build -t server-stib-frontend:latest ./stibFront

# Deploy
./deploy.sh
```

**What `deploy.sh` does:**

1. Saves Docker images as gzip tarballs
2. Transfers images + `docker-compose.yml` to the server via SCP
3. On server: reads `API_BASE_URL` from `/root/.env` → writes `runtime-env.js`
4. Loads images, runs `docker compose up -d`
5. Waits for DB readiness, runs `alembic upgrade head`
6. Cleans up tarballs and dangling images

### Docker commands

```bash
docker compose ps
docker compose logs -f api
docker compose up -d --build api    # rebuild and restart only the API
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
cd fastapi-server
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
# Review the generated file in fastapi-server/migrations/versions/
python -m alembic upgrade head
```

### Fresh database (first-time)

```bash
# Start the stack (SQLAlchemy creates tables on startup)
docker compose up -d --build

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
git clone git@github.com:a-trillet/server-STIB.git
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
