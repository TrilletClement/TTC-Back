#!/bin/bash

# --- CONFIGURATION ---
DOCKER_SERVER_IP="192.168.14.14"
DOCKER_SERVER_USER="clement"
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
docker save $API_IMAGE   | gzip > api.tar.gz

echo "2. Compression des fichiers de configuration CA..."
# Bundle CA config files (setup script + OpenSSL configs only — NOT the
# generated keys, which live permanently on the server and are gitignored).
tar czf ca-config.tar.gz \
    ca/setup-ca.sh \
    ca/openssl-root.cnf \
    ca/openssl-inter.cnf

echo "3. Transfert vers le serveur Docker ($DOCKER_SERVER_IP)..."
# .env is NOT transferred — the server keeps its own prod .env.
scp front.tar.gz api.tar.gz docker-compose.yml \
    ca-config.tar.gz \
    scripts/db-backup.sh \
    $DOCKER_SERVER_USER@$DOCKER_SERVER_IP:/tmp/

echo "4. Installation sur le serveur Docker..."
ssh -t $DOCKER_SERVER_USER@$DOCKER_SERVER_IP "su - root -c '
    mv /tmp/front.tar.gz /tmp/api.tar.gz /tmp/docker-compose.yml /root/

    echo \"--- Installation du script de backup automatique ---\"
    mkdir -p /root/scripts
    mv /tmp/db-backup.sh /root/scripts/db-backup.sh
    chmod +x /root/scripts/db-backup.sh
    CRON_LINE=\"0 3 * * * /root/scripts/db-backup.sh >> /root/db-backups/backup.log 2>&1\"
    ( crontab -l 2>/dev/null | grep -v \"db-backup.sh\"; echo \"\$CRON_LINE\" ) | crontab -
    echo \"  Cron installé : \$CRON_LINE\"

    echo \"--- Extraction de la config CA ---\"
    mkdir -p /root/ca
    tar xzf /tmp/ca-config.tar.gz -C /root/
    chmod +x /root/ca/setup-ca.sh
    rm /tmp/ca-config.tar.gz

    echo \"--- Configuration de l environnement frontend ---\"
    mkdir -p /root/stibFront/public
    API_URL=\$(grep \"^API_BASE_URL=\" /root/.env 2>/dev/null | cut -d= -f2-)
    API_URL=\${API_URL:-https://transport.trillet.be}
    echo \"window.__env = {\\\"API_BASE_URL\\\":\\\"\${API_URL}\\\"};\" > /root/stibFront/public/runtime-env.js
    echo \"  runtime-env.js → API_BASE_URL=\${API_URL}\"

    echo \"--- Chargement des images ---\"
    docker load < front.tar.gz
    docker load < api.tar.gz

    echo \"--- Initialisation de la CA (si premiere fois) ---\"
    if [ ! -f /root/ca/intermediate/certs/ca-chain.pem ]; then
        echo \"  CA not found — running setup-ca.sh ...\"
        bash /root/ca/setup-ca.sh
        echo \"\"
        echo \"  *** IMPORTANT: copy the Root CA key to USB and delete it! ***\"
        echo \"  cp /root/ca/root/private/ca.key /path/to/usb/\"
        echo \"  shred -u /root/ca/root/private/ca.key\"
        echo \"\"
    else
        echo \"  CA already initialised, skipping.\"
    fi

    echo \"--- Sauvegarde de la base de donnees ---\"
    DUMP_DIR=/root/db-backups
    mkdir -p \$DUMP_DIR
    DUMP_FILE=\"\$DUMP_DIR/dump_\$(date +%Y%m%d_%H%M%S).sql.gz\"
    if docker compose ps -q db 2>/dev/null | grep -q .; then
        docker compose exec -T db pg_dump -U mylocaldb mylocaldb | gzip > \"\$DUMP_FILE\"
        echo \"  Backup: \$DUMP_FILE (\$(du -sh \"\$DUMP_FILE\" | cut -f1))\"
        ls -t \"\$DUMP_DIR\"/dump_*.sql.gz 2>/dev/null | tail -n +11 | xargs rm -f
        echo \"  (anciens backups > 10 supprimes)\"
    else
        echo \"  DB non demarree — backup ignore.\"
    fi

    echo \"--- Relance des services ---\"
    docker compose up -d

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
    echo \"Serveur Docker: deploiement termine !\"
'"

echo "5. Nettoyage local..."
rm -f front.tar.gz api.tar.gz ca-config.tar.gz

echo ""
echo "=== Deploiement termine ==="
echo "  API:      https://transport.trillet.be/api/"
echo "  Frontend: https://transport.trillet.be/"
