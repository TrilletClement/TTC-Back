#!/bin/bash

# --- CONFIGURATION ---
SERVER_IP="192.168.14.14"
SERVER_USER="clement"
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
    echo \"--- Chargement des images ---\"
    docker load < front.tar.gz
    docker load < api.tar.gz
    echo \"--- Migrations Alembic ---\"
    docker compose run --rm api alembic upgrade head
    echo \"--- Relance des services ---\"
    docker compose up -d
    echo \"--- Nettoyage ---\"
    rm front.tar.gz api.tar.gz
    docker image prune -f
    echo \"Deploiement termine avec succes !\"
'"


# SI on fait cette merde c'est censé bien fonctionner :
# cd ~/projets/server-STIB
# docker-compose up -d --build
# docker compose up
# ./deploy.sh 