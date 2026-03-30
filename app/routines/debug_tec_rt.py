#!/usr/bin/env python3
import os
import requests
from google.transit import gtfs_realtime_pb2
from google.protobuf.json_format import MessageToJson

# Configuration
TEC_API_KEY = os.environ.get("TEC_API_KEY", "36497DD5F3AD4262B24981633E73EF33")
REALTIME_URL = "https://gtfsrt.tectime.be/proto/RealTime/vehicles"

try:
    # On ajoute un User-Agent pour éviter d'être bloqué par certains WAF
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(REALTIME_URL, params={"key": TEC_API_KEY}, headers=headers, timeout=15)
    response.raise_for_status()
    
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(response.content)

    print(f"--- INFO FLUX ---")
    print(f"Timestamp du flux : {feed.header.timestamp}")
    print(f"Nombre d'entités  : {len(feed.entity)}\n")

    print("=== DUMP COMPLET DES DONNÉES (Format JSON) ===\n")
    
    for entity in feed.entity:
        # MessageToJson est la fonction correcte pour transformer le binaire en JSON lisible
        print(MessageToJson(entity))
        print("-" * 40)

except Exception as e:
    print(f"Erreur lors de l'exécution : {e}")