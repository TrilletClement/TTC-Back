#!/bin/bash

# --- CONFIGURATION ---
SERVER_IP="192.168.14.14"
SERVER_USER="clement"
API_IMAGE="stib-api:latest"
FRONT_IMAGE="server-stib-frontend:latest"

echo "1. Sauvegarde et compression des images Docker..."
docker save $FRONT_IMAGE | gzip > front.tar.gz
docker save $API_IMAGE   | gzip > api.tar.gz

echo "2. Compression des fichiers de configuration..."
# Bundle CA config files (setup script + OpenSSL configs only — NOT the
# generated keys, which live permanently on the server and are gitignored).
tar czf ca-config.tar.gz \
    ca/setup-ca.sh \
    ca/openssl-root.cnf \
    ca/openssl-inter.cnf

# Bundle nginx config
tar czf nginx-config.tar.gz nginx/nginx.conf

echo "3. Transfert vers le serveur ($SERVER_IP)..."
# .env is NOT transferred — the server keeps its own prod .env.
# To set up a new server: ssh in and create /root/.env from .env.example.
scp front.tar.gz api.tar.gz docker-compose.yml \
    ca-config.tar.gz nginx-config.tar.gz \
    $SERVER_USER@$SERVER_IP:/tmp/

echo "4. Installation sur le serveur..."
ssh -t $SERVER_USER@$SERVER_IP "su - root -c '
    mv /tmp/front.tar.gz /tmp/api.tar.gz /tmp/docker-compose.yml /root/

    echo \"--- Extraction des configs CA et nginx ---\"
    mkdir -p /root/ca /root/nginx
    tar xzf /tmp/ca-config.tar.gz    -C /root/
    tar xzf /tmp/nginx-config.tar.gz -C /root/
    chmod +x /root/ca/setup-ca.sh
    rm /tmp/ca-config.tar.gz /tmp/nginx-config.tar.gz

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

    echo \"--- Relance des services ---\"
    docker compose up -d

    echo \"--- Attente que la base de donnees soit prete ---\"
    until docker compose exec -T db pg_isready -U mylocaldb > /dev/null 2>&1; do
        echo \"  DB not ready, waiting...\"
        sleep 2
    done

    echo \"--- Application des migrations Alembic ---\"
    docker compose exec -T api sh -c \"cd /app && python -m alembic upgrade head\"

    echo \"--- Nettoyage ---\"
    rm front.tar.gz api.tar.gz
    docker image prune -f
    echo \"Deploiement termine avec succes !\"
'"

echo "5. Nettoyage local..."
rm -f front.tar.gz api.tar.gz ca-config.tar.gz nginx-config.tar.gz
