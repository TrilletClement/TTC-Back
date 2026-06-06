#!/bin/bash

# --- CONFIGURATION ---
SERVER_IP="192.168.14.14"
SERVER_USER="clement"
API_IMAGE="stib-api:latest"
FRONT_IMAGE="server-stib-frontend:latest"

CLEAN_IMPORT=false
if [ "$1" == "--import" ] || [ "$1" == "-i" ]; then
    CLEAN_IMPORT=true
    echo "⚠️ Option --import détectée : La DB sera vidée et les imports GTFS seront lancés."
fi

echo "0. Build des images Docker..."
docker compose build

echo "1. Sauvegarde et compression des images Docker..."
docker save $FRONT_IMAGE | gzip > front.tar.gz
docker save $API_IMAGE | gzip > api.tar.gz

echo "2. Transfert vers le serveur ($SERVER_IP)..."
scp front.tar.gz api.tar.gz docker-compose.yml $SERVER_USER@$SERVER_IP:/tmp/

echo "3. Installation sur le serveur..."
ssh -t $SERVER_USER@$SERVER_IP "su - root -c '
    mv /tmp/front.tar.gz /tmp/api.tar.gz /tmp/docker-compose.yml /root/
    cd /root/
    echo \"--- Configuration de l environnement frontend ---\"
    mkdir -p /root/stibFront/public
    API_URL=\$(grep \"^API_BASE_URL=\" /root/.env 2>/dev/null | cut -d= -f2-)
    API_URL=\${API_URL:-https://transport.trillet.be}
    echo \"window.__env = {\\\"API_BASE_URL\\\":\\\"\${API_URL}\\\"};\" > /root/stibFront/public/runtime-env.js
    echo \"  runtime-env.js → API_BASE_URL=\${API_URL}\"
    echo \"--- Chargement des images ---\"
    docker load < front.tar.gz
    docker load < api.tar.gz
    echo \"--- Relance des services ---\"
    docker compose up -d --force-recreate
    echo \"--- Attente que la base de donnees soit prete ---\"
    until docker compose exec -T db pg_isready -U mylocaldb > /dev/null 2>&1; do
        echo \"  DB not ready, waiting...\"
        sleep 2
    done
    echo \"--- Fix de la table alembic_version ---\"
    docker compose exec -T db psql -U mylocaldb -c \"ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64);\" 2>/dev/null || true
    if [ \"$CLEAN_IMPORT\" = \"true\" ]; then
        echo \"--- NETTOYAGE DES TABLES DE TRANSPORT ---\"
        docker compose exec -T db psql -U mylocaldb -c \"TRUNCATE TABLE raw_gtfs_service_date, raw_gtfs_stop_time, raw_gtfs_trip, realtime_stop_time_override, stop, line, agency CASCADE;\"
    fi
    echo \"--- Application des migrations Alembic ---\"
    docker compose exec -T api sh -c \"cd /app && python -m alembic upgrade head\"
    if [ \"$CLEAN_IMPORT\" = \"true\" ]; then
        echo \"--- Lancement des imports GTFS ---\"
        docker compose exec -T api sh -c \"python -m app.routines.stib_import\"
        docker compose exec -T api sh -c \"python -m app.routines.tec_import\"
        docker compose exec -T api sh -c \"python -m app.routines.delijn_import\"
        docker compose exec -T api sh -c \"python -m app.routines.sncb_import\"
    fi
    echo \"--- Nettoyage ---\"
    rm front.tar.gz api.tar.gz
    docker image prune -f
    echo \"Deploiement termine avec succes !\"
'"