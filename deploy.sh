#!/bin/bash

# --- CONFIGURATION ---
SERVER_IP="192.168.14.14"
SERVER_USER="clement"
API_IMAGE="clemzi/stib-api:1.0"
FRONT_IMAGE="server-stib-frontend:latest"

echo "1. Sauvegarde des images Docker..."
docker save $FRONT_IMAGE > front.tar
docker save $API_IMAGE > api.tar

echo "2. Transfert vers le serveur ($SERVER_IP)..."
# On envoie tout dans /tmp
scp .env front.tar api.tar docker-compose.yml $SERVER_USER@$SERVER_IP:/tmp/

echo "3. Installation sur le serveur..."
# On se connecte et on exécute les commandes à distance
# Note : Il faudra taper ton mot de passe quand SSH le demandera
ssh -t $SERVER_USER@$SERVER_IP "su - root -c '
    mv /tmp/front.tar /tmp/api.tar /tmp/docker-compose.yml /tmp/.env /root/ 
    cd /root/
    docker load < front.tar
    docker load < api.tar
    docker compose up -d
    rm front.tar api.tar
    docker image prune -f
    echo \"Deploiement termine avec succes !\"
'"