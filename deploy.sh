#!/bin/bash

# --- CONFIGURATION ---
SERVER_IP="192.168.14.14"
SERVER_USER="antoine"
API_IMAGE="stib-api:latest"
FRONT_IMAGE="server-stib-frontend:latest"

echo "1. Sauvegarde et compression des images Docker..."
# L'utilisation de gzip reduit la taille de 700Mo a environ 200Mo
docker save $FRONT_IMAGE | gzip > front.tar.gz
docker save $API_IMAGE | gzip > api.tar.gz

echo "2. Transfert vers le serveur ($SERVER_IP)..."
# Ajout de runtime-env.js dans le transfert
scp .env front.tar.gz api.tar.gz docker-compose.yml $SERVER_USER@$SERVER_IP:/tmp/

echo "3. Installation sur le serveur..."
ssh -t $SERVER_USER@$SERVER_IP "su - root -c '
    mv /tmp/front.tar.gz /tmp/api.tar.gz /tmp/docker-compose.yml /tmp/.env /root/
    cd /root/
    echo \"--- Configuration de l environnement frontend --- \"
    rm -rf /root/stibFront/public/runtime-env.js
    mkdir -p /root/stibFront/public
    echo '\''window.__env = {"API_BASE_URL":"https://transport.trillet.be"};'\'' > /root/stibFront/public/runtime-env.js
    echo \"--- Chargement des images --- \"
    docker load < front.tar.gz
    docker load < api.tar.gz
    echo \"--- Relance des services --- \"
    docker compose up -d
    echo \"--- Attente que la base de donnees soit prete --- \"
    until docker compose exec -T db pg_isready -U mylocaldb > /dev/null 2>&1; do
        echo \"  DB not ready, waiting...\"
        sleep 2
    done
    echo \"--- Application des migrations Alembic --- \"
    docker compose exec -T api sh -c \"cd /app && python -m alembic upgrade head\"
    echo \"--- Nettoyage --- \"
    rm front.tar.gz api.tar.gz
    docker image prune -f
    echo \"Deploiement termine avec succes !\"
'"


# SI on fait cette merde c'est censé bien fonctionner :
# cd ~/projets/server-STIB
# docker-compose up -d --build
# docker compose up
# ./deploy.sh 