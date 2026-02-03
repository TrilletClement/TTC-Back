# Server STIB - Complete Installation Guide

This guide provides step-by-step instructions to clone and run the Server STIB project on a new development machine.

## Prerequisites

- Ubuntu/Debian Linux (or WSL2 on Windows)
- Sudo access
- GitHub account with repository access
- Access to the production PostgreSQL database (192.168.14.13)

## Table of Contents

1. [SSH Configuration for GitHub](#1-ssh-configuration-for-github)
2. [Clone the Project](#2-clone-the-project)
3. [System Dependencies Installation](#3-system-dependencies-installation)
4. [Python Environment Setup](#4-python-environment-setup)
5. [Frontend Configuration](#5-frontend-configuration)
6. [Database Configuration](#6-database-configuration)
7. [PM2 Configuration](#7-pm2-configuration)
8. [Starting Services](#8-starting-services)
9. [Verification](#9-verification)
10. [Troubleshooting](#10-troubleshooting)

---

## Initial Setup

After cloning the repository, create your local PM2 configuration:

```bash
# Copy the template
cp ecosystem.config.js.template ecosystem.config.js

# Replace YOUR_USERNAME with your actual username
sed -i 's/YOUR_USERNAME/clement/g' ecosystem.config.js

# Or edit manually
nano ecosystem.config.js
```

## 1. SSH Configuration for GitHub

### Generate an SSH Key (if needed)

```bash
# Check if a key already exists
ls ~/.ssh

# If needed, generate a new ED25519 key
ssh-keygen -t ed25519 -C "your.email@example.com"
```

### Configure SSH Agent

```bash
# Start SSH agent
eval "$(ssh-agent -s)"

# Add your private key
ssh-add ~/.ssh/id_ed25519

# Verify the key is added
ssh-add -l
```

### Add Public Key to GitHub

```bash
# Display your public key
cat ~/.ssh/id_ed25519.pub
```

1. Copy the complete output
2. Go to GitHub → Settings → SSH and GPG keys → New SSH key
3. Paste the key and save

### Test Connection

```bash
ssh -T git@github.com
# Expected: "Hi username! You've successfully authenticated..."
```

---

## 2. Clone the Project

```bash
cd ~/projets  # or your preferred directory
git clone git@github.com:a-trillet/server-STIB.git
cd server-STIB
```

---

## 3. System Dependencies Installation

### Install Node.js and npm (NodeSource, Node 20+)

Angular CLI requires Node v20.19+ or v22.12+. Use NodeSource to install a recent version:

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Verify versions (should be 20.x+)
node -v
npm -v
```

### Install PM2 (Process Manager)

```bash
sudo npm install -g pm2

# Verify installation
pm2 -v
```

### install Angular stuff

```bash
cd stibFront
sudo npm install
sudo npm install -g @angular/cli
```

### Install Python Dependencies

```bash
# Install required development tools
sudo apt install python3.10-venv libpq-dev python3-dev build-essential -y
```

---

## 4. Python Environment Setup

### Create Virtual Environment

```bash
python3 -m venv venv
```

### Activate Virtual Environment

```bash
source venv/bin/activate
```

### Install Python Packages

```bash
# Update pip
pip install --upgrade pip

# Install all dependencies
pip install -r requirements.txt
```

---

## 5. Database Configuration (NOT NOW)

```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo service postgresql start
sudo -u postgres psql -c "CREATE USER mylocaldb WITH PASSWORD 'mylocaldb';"
sudo -u postgres psql -c "CREATE DATABASE mylocaldb OWNER mylocaldb;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE mylocaldb TO mylocaldb;"

# sysVinit: 
sudo update-rc.d postgresql defaults
sudo service postgresql start

# systemd:
sudo systemctl enable postgresql
sudo systemctl start postgresql

```

## 6. PM2 Configuration

### Update ecosystem.config.js

modify ecosystem.config.js to reflect your paths and environment:

## 7. Starting Services

### Start All Services with PM2

```bash
# start all services defined in ecosystem.config.js
pm2 start ecosystem.local.config.js

# Save PM2 process list
pm2 save
```

### Useful PM2 Commands

```bash
# View all processes status
pm2 status

# View real-time logs for all services
pm2 logs

# View logs for specific service
pm2 logs stib-frontend
pm2 logs stib-api
pm2 logs stib-imports

# Restart all services
pm2 restart all

# Restart specific service
pm2 restart stib-frontend

# Stop all services
pm2 stop all

# Delete all processes
pm2 delete all

# Save PM2 configuration
pm2 save

# Configure PM2 to start on system boot
pm2 startup
```

---

## 8. Verification

### Check Service Status

All three services should show status **"online"**:

```bash
pm2 status
```

Expected output:

```
┌────┬────────────────┬──────┬────────┬─────────┬──────────┐
│ id │ name           │ mode │ ↺      │ status  │ memory   │
├────┼────────────────┼──────┼────────┼─────────┼──────────┤
│ 0  │ stib-frontend  │ fork │ 0      │ online  │ 125.0mb  │
│ 1  │ stib-api       │ fork │ 0      │ online  │ 89.5mb   │
│ 2  │ stib-imports   │ fork │ 0      │ online  │ 67.2mb   │
└────┴────────────────┴──────┴────────┴─────────┴──────────┘
```

### Access the Application

Services should be accessible at:

- **Angular Frontend**: <http://localhost:4200>
- **Flask API** (direct): <http://localhost:5000>
- **FastAPI**: <http://localhost:8001>
- **API via Proxy**: <http://localhost:4200/api> (proxied to localhost:5000)

### Test API Endpoints

```bash
# Test Flask API health
curl http://localhost:5000/

# Test through Angular proxy
curl http://localhost:4200/api/
```

---

## 9. Troubleshooting

### Angular CLI requires newer Node.js

If `pm2 logs stib-frontend` shows a message like "Angular CLI requires a minimum Node.js version of v20.19 or v22.12", update Node.js to 20+ using NodeSource:

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
node -v
```

### "ModuleNotFoundError: No module named 'google'"

Install the missing GTFS package:

```bash
source venv/bin/activate
pip install gtfs-realtime-bindings
echo "gtfs-realtime-bindings==2.0.0" >> requirements.txt
pm2 restart stib-imports
```

### "Script not found" Error in PM2

Verify that:

- Paths in `ecosystem.config.js` match your system
- Virtual environment is activated
- Dependencies are installed

```bash
# Check if binaries exist
source venv/bin/activate
which gunicorn
which uvicorn
ls stibFront/node_modules/.bin/ng
```

### "Error: spawn .../node_modules/.bin/ng ENOENT"

This means PM2 tried to start Angular but the `ng` executable cannot be resolved from `node_modules` (broken install / missing files).

```bash
cd stibFront
node scripts/start-frontend.js version
```

If it still fails, reinstall frontend dependencies:

```bash
cd stibFront
rm -rf node_modules
npm ci
```

### STIB realtime ↔ GTFS mismatch files

When the scheduler fetches STIB realtime (`vehicle-position-rt-production`) and cannot match it to a GTFS trip/stop, it writes deduplicated mismatch entries to:

- `server-STIB/logs/missed_buses/direction_not_in_gtfs.json`
- `server-STIB/logs/missed_buses/stop_not_in_gtfs.json`
- `server-STIB/logs/missed_buses/no_trips.json`
- `server-STIB/logs/missed_buses/no_tripstop.json`

### psycopg2 Installation Error

```bash
sudo apt install libpq-dev python3-dev build-essential
pip install psycopg2-binary
```

### Database Connection Error

```bash
# Test connectivity
nc -zv 192.168.14.13 5432

# Check database URL in shared/db.py
cat shared/db.py | grep DATABASE_URL

# Verify credentials are correct
```

### CORS Errors

If you see CORS errors in the browser console:

1. Verify the proxy configuration in `stibFront/proxy.conf.json`
2. Check that Angular is using the proxy: `pm2 logs stib-frontend`
3. Ensure Flask CORS is configured in `flask-web-server/config.py`

### Angular Build Errors

```bash
cd stibFront

# Clean install
rm -rf node_modules package-lock.json
npm cache clean --force
npm install

cd ..
pm2 restart stib-frontend
```

### Git Wants to Commit node_modules or venv

Create/update `.gitignore`:

```bash
cat >> .gitignore << 'EOF'
# Dependencies
node_modules/
venv/

# IDE
.vscode/
.idea/

# Environment
.env
*.log

# Build
dist/
build/
*.pyc
__pycache__/

# PM2
.pm2/
EOF

# Remove from git cache
git rm -r --cached node_modules/ venv/ .vscode/ 2>/dev/null || true
```

---

## Project Architecture

```
server-STIB/
├── stibFront/              # Angular application (frontend)
│   ├── src/
│   │   └── environments/   # Environment configurations
│   ├── proxy.conf.json     # Proxy configuration for dev server
│   └── package.json        # Node.js dependencies
├── flask-web-server/       # Flask API (main backend)
│   ├── app/
│   ├── config.py           # Flask configuration
│   └── requirements.txt    # Python dependencies
├── fastapi-server/         # FastAPI (imports service)
│   └── app/
├── shared/                 # Shared modules
│   └── db.py               # Database configuration
├── venv/                   # Python virtual environment
├── ecosystem.config.js     # PM2 process configuration
├── requirements.txt        # Main Python dependencies
└── .gitignore             # Git ignore patterns
```

---

## Development Workflow

### Daily Development

```bash
# Navigate to project
cd ~/projets/server-STIB

# Activate Python environment
source venv/bin/activate

# Check service status
pm2 status

# View logs if needed
pm2 logs

# Work on your code...

# Restart services after changes
pm2 restart stib-api        # For Flask changes
pm2 restart stib-imports    # For FastAPI changes
# Frontend hot-reloads automatically
```

### Before Committing

```bash
# Deactivate virtual environment
deactivate

# Check what's being committed
git status

# Ensure node_modules and venv are not included
git add .
git commit -m "your commit message"
git push
```

---

## Notes

- **Always activate the virtual environment** before working on Python code: `source venv/bin/activate`
- **Deactivate** when done: `deactivate`
- **PM2 logs are essential** for debugging: `pm2 logs [service-name]`
- **Proxy configuration** allows the frontend to call `/api/*` without CORS issues
- **Database** is on the production server (192.168.14.13), not local
- **Environment files** determine which API URL to use (local proxy vs production)

---

## Authors

Clément Trillet
