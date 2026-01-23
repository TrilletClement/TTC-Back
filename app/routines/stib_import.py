#!/usr/bin/env python3
if __name__ == "__main__":
    import sys, os
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../'))
    sys.path.insert(0, BASE_DIR)
    FASTAPI_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
    sys.path.insert(0, FASTAPI_DIR)

import requests
import hashlib
from sqlalchemy.orm import Session
import sqlalchemy as sa
from shared.models import Line, Agency, Stop, Trip, TripStop, GTFSTrip
from shared.db import get_db
import json
import csv
import time
import re
from io import StringIO
from collections import defaultdict
import os
import sys
from app.routines import tec_import

STIB_API_KEY = os.environ.get("STIB_API_KEY", "").strip()
STIB_HEADERS = {"Authorization": f"Apikey {STIB_API_KEY}"} if STIB_API_KEY else {}


def normalize_stib_id(stop_id):
    digits = re.sub(r'[A-Z]+$', '', str(stop_id))
    return digits.zfill(4) if len(digits) < 4 else digits

def get_stib_agency(session):
    stib = session.query(Agency).filter_by(name="STIB").first()
    if not stib:
        stib = Agency(name="STIB", country="Belgium")
        session.add(stib)
        session.commit()
    return stib


def import_stib_lines(response):
    tic = time.time()
    reader = csv.DictReader(StringIO(response.content.decode('utf-8')))
    
    with get_db() as session:
        get_stib_agency(session)
        for row in reader:
            short_name = row.get("route_short_name")
            if not short_name: continue

            # Recherche intelligente (gestion des doublons de noms longs)
            existing_lines = session.query(Line).filter_by(short_name=short_name, agency_name="STIB").all()
            target_line = next((l for l in existing_lines if l.long_name == row.get("route_long_name")), None)
            
            if not target_line and len(existing_lines) == 1:
                target_line = existing_lines[0]

            data = {
                "route_id": row.get("route_id"),
                "short_name": short_name,
                "long_name": row.get("route_long_name"),
                "route_type": row.get("route_type"),
                "color": "#" + row.get("route_color", "000000").zfill(6),
                "text_color": "#" + row.get("route_text_color", "FFFFFF").zfill(6),
                "agency_name": "STIB"
            }

            if target_line:
                for key, value in data.items(): setattr(target_line, key, value)
            else:
                session.add(Line(**data))
        
        session.commit()
    print(f"STIB Lines updated in {time.time() - tic:.2f}s")

def import_stib_stops(response):
    tic = time.time()
    reader = csv.DictReader(StringIO(response.content.decode('utf-8')))
    with get_db() as session:
        get_stib_agency(session)
        for row in reader:
            sid, name = row.get("stop_id"), row.get("stop_name")
            if not sid: continue
            stop = session.query(Stop).filter_by(stop_id=sid, agency_name="STIB").first()
            if stop: stop.name = name
            else: session.add(Stop(stop_id=sid, name=name, agency_name="STIB"))
        session.commit()
    print(f"STIB Stops updated in {time.time() - tic:.2f}s")
    
def import_trips(trips_reader, stop_times_reader):
    tic = time.time()
    
    def build_signature(line_id, direction, stop_ids):
        payload = f"{line_id}:{direction}|" + "|".join(stop_ids)
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    # 1. Grouper les données du CSV en mémoire
    trip_data = {row["trip_id"]: {"route_id": row["route_id"], "dir": int(row.get("direction_id", 0)), "stops": []} 
                 for row in trips_reader}
    
    for row in stop_times_reader:
        if row["trip_id"] in trip_data:
            trip_data[row["trip_id"]]["stops"].append((int(row["stop_sequence"]), row["stop_id"]))

    with get_db() as session:
        agency_name = "STIB"
        
        # Mapping route_id (GTFS) -> line_id (DB)
        route_to_line = {l.route_id: l.id for l in session.query(Line).filter_by(agency_name=agency_name).all()}
        # Mapping gtfs_id -> trip_id existant
        existing_gtfs_trips = {gt.id: gt.trip_id for gt in session.query(GTFSTrip).all()}
        # Mapping signature -> trip_id
        sig_to_trip_id = {t.signature: t.id for t in session.query(Trip.id, Trip.signature).filter_by(line_agency_name=agency_name).all()}

        new_trips_to_create = {} # signature -> Trip object
        gtfs_mappings_to_add = []
        sig_counts = defaultdict(int)

        # 2. Identifier ce qui est nouveau
        for g_id, info in trip_data.items():
            l_id = route_to_line.get(info["route_id"])
            if not l_id or not info["stops"]: continue
            
            # Trier les arrêts par séquence et extraire les IDs
            ordered_stops = [s[1] for s in sorted(info["stops"])]
            sig = build_signature(l_id, info["dir"], ordered_stops)
            sig_counts[sig] += 1

            if g_id not in existing_gtfs_trips:
                if sig not in sig_to_trip_id and sig not in new_trips_to_create:
                    new_trips_to_create[sig] = Trip(
                        line_id=l_id, line_agency_name=agency_name,
                        direction=info["dir"], signature=sig,
                        start_stop_id=ordered_stops[0], terminus_stop_id=ordered_stops[-1],
                        start_agency_name=agency_name, terminus_agency_name=agency_name
                    )
                gtfs_mappings_to_add.append((g_id, sig))

        # 3. Sauvegarde des nouveaux Trips et TripStops
        if new_trips_to_create:
            session.add_all(new_trips_to_create.values())
            session.flush() # Pour avoir les IDs des nouveaux trips
            
            ts_to_insert = []
            for sig, trip in new_trips_to_create.items():
                sig_to_trip_id[sig] = trip.id
                # On récupère les stops depuis le premier trip qui a généré cette signature
                sample_gtfs_id = next(g for g, s in gtfs_mappings_to_add if s == sig)
                for idx, (_, s_id) in enumerate(sorted(trip_data[sample_gtfs_id]["stops"])):
                    ts_to_insert.append({"trip_id": trip.id, "stop_stop_id": s_id, "stop_agency_name": agency_name, "sequence": idx})
            session.bulk_insert_mappings(TripStop, ts_to_insert)

        # 4. Mettre à jour GTFSTrip et les Trip Counts
        if gtfs_mappings_to_add:
            session.bulk_insert_mappings(GTFSTrip, [
                {"id": g_id, "trip_id": sig_to_trip_id[sig]} for g_id, sig in gtfs_mappings_to_add
            ])
        
        # Update counts
        session.bulk_update_mappings(Trip, [
            {"id": sig_to_trip_id[s], "trip_count": c} for s, c in sig_counts.items() if s in sig_to_trip_id
        ])

        # 5. Calcul des "Best Trips" (Une seule grosse requête au lieu d'une boucle)
        # On cherche le trip qui a le plus d'arrêts (max sequence) * son nombre de passages
        best_trips_query = session.query(
            Trip.line_id, Trip.direction, Trip.id,
            (sa.func.max(TripStop.sequence) * Trip.trip_count).label("score")
        ).join(TripStop).filter(Trip.line_agency_name == agency_name).group_by(Trip.id).subquery()

        # On prend le meilleur score par (line_id, direction)
        for line in session.query(Line).filter_by(agency_name=agency_name).all():
            for d in [0, 1]:
                best = session.query(best_trips_query.c.id).filter(
                    best_trips_query.c.line_id == line.id, 
                    best_trips_query.c.direction == d
                ).order_by(best_trips_query.c.score.desc()).first()
                if best:
                    setattr(line, f"best_trip_{d}_id", best.id)

        session.commit()
        print(f"Import terminé en {time.time() - tic:.2f}s")

def normalize_stib_id(stop_id):
    digits = re.sub(r'[A-Z]+$', '', str(stop_id))
    if len(digits) < 4:
        digits = digits.zfill(4)
    return digits

def get_all_incoming_buses_export():
    tic = time.time()
    export_url = "https://data.stib-mivb.brussels/api/explore/v2.1/catalog/datasets/vehicle-position-rt-production/exports/json"
    
    print(f"[{time.strftime('%H:%M:%S')}] Démarrage mise à jour Temps Réel STIB...")
    
    try:
        response = requests.get(export_url, headers=STIB_HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"ERREUR API: Code {response.status_code}")
            return
        
        data = response.json()
        
        #SPOILER BEN FAUT CHANGER CA
        map_path = "/home/c.trillet/server-STIB/fastapi-server/app/routines/missed_buses/mapping.json" 
        mapping_dict = {}
        if os.path.exists(map_path):
            with open(map_path, "r") as f:
                mapping_dict = {row[0]: row[1] for row in json.load(f)}
        print(f"DEBUG: Mapping chargé pour {len(mapping_dict)} terminus.")

        with get_db() as session:
            # 1. Chargement Références
            all_stib_lines = session.query(Line).filter_by(agency_name="STIB").all()
            line_map = defaultdict(list)
            for l in all_stib_lines: 
                line_map[l.short_name].append(l.id)

            tripstops = (session.query(TripStop.id, TripStop.trip_id, TripStop.sequence, TripStop.stop_stop_id, 
                                     Trip.line_id, Trip.terminus_stop_id).join(Trip)
                         .filter(Trip.line_agency_name == "STIB").all())

            ts_map = defaultdict(list)
            tripstop_next_map = {}
            suffixes = ['', 'A', 'B', 'F', 'G', 'H']

            for ts in tripstops:
                n_term, n_stop = normalize_stib_id(ts.terminus_stop_id), normalize_stib_id(ts.stop_stop_id)
                for t_suf in suffixes:
                    for s_suf in suffixes:
                        key = (ts.line_id, f"{n_term}{t_suf}" if t_suf else n_term, f"{n_stop}{s_suf}" if s_suf else n_stop)
                        ts_map[key].append((ts.id, ts.trip_id, ts.sequence))
                tripstop_next_map[(ts.trip_id, ts.sequence)] = ts.id

            # 2. Traitement des positions
            incoming_ids = set()
            count_per_line = defaultdict(int)

            for entry in data:
                l_short = entry.get('lineid')
                l_ids = line_map.get(l_short)
                if not l_ids: continue
                
                v_pos = json.loads(entry['vehiclepositions']) if isinstance(entry['vehiclepositions'], str) else entry['vehiclepositions']
                
                for pos in v_pos:
                    # Normalisation Direction et Point
                    raw_dir = normalize_stib_id(pos['directionId'])
                    t_id = mapping_dict.get(raw_dir, raw_dir)
                    s_id = normalize_stib_id(pos['pointId'])
                    
                    found_match = False
                    for lid in l_ids:
                        # Test de correspondance exacte ou partielle (4 premiers chiffres)
                        match_keys = [(lid, t_id, s_id)]
                        # Si pas de match direct, on tente le t_id sans suffixe
                        if len(t_id) > 4: match_keys.append((lid, t_id[:4], s_id))

                        for key in match_keys:
                            if key in ts_map:
                                for tsid, tid, seq in ts_map[key]:
                                    found_match = True
                                    if pos['distanceFromPoint'] == "0" or pos['distanceFromPoint'] == 0:
                                        incoming_ids.add(tsid)
                                    else:
                                        nxt = tripstop_next_map.get((tid, seq + 1))
                                        if nxt: incoming_ids.add(nxt)
                    
                    if found_match:
                        count_per_line[l_short] += 1

            # 3. Persistence
            session.query(TripStop).filter(TripStop.stop_agency_name == "STIB").update({TripStop.vehicle_incoming: False}, synchronize_session=False)
            if incoming_ids:
                session.query(TripStop).filter(TripStop.id.in_(list(incoming_ids))).update({TripStop.vehicle_incoming: True}, synchronize_session=False)
            
            session.commit()
            
            print(f"Résultat: {len(incoming_ids)} TripStops marqués 'incoming'.")
            for line, count in count_per_line.items():
                if count > 0: print(f" - Ligne {line}: {count} positions appariées")
            
            print(f"Update STIB RT terminée en {time.time()-tic:.2f}s")

    except Exception as e:
        print(f"ERREUR CRITIQUE RT: {e}")
        import traceback
        traceback.print_exc()
        
        
def import_stib_gtfs():
    # lines
    routes_url = "https://data.stib-mivb.brussels/api/explore/v2.1/catalog/datasets/gtfs-files-production/files/92c45d9df99624d7e05e9ade35ba0ce8"
    route_response = requests.get(routes_url)

    if route_response.status_code != 200:
        print(f"HTTP error {route_response.status_code}: {route_response.text}")
        return
    
    # stops
    stops_url = "https://data.stib-mivb.brussels/api/explore/v2.1/catalog/datasets/gtfs-files-production/files/7068c8d492df76c5125fac081b5e09e9"
    stop_response = requests.get(stops_url)

    if stop_response.status_code != 200:
        print(f"HTTP error {stop_response.status_code}: {stop_response.text}")
        return
    
    # trips & stop_times
    trips_url = "https://data.stib-mivb.brussels/api/explore/v2.1/catalog/datasets/gtfs-files-production/files/7831854a320cbf4ea5b6b327cd4581af"
    stop_times_url = "https://data.stib-mivb.brussels/api/explore/v2.1/catalog/datasets/gtfs-files-production/files/3cc9124c230b72e07df09e27c59eba88"
    
    # Fetch CSVs
    trips_csv = requests.get(trips_url).content.decode("utf-8")
    stop_times_csv = requests.get(stop_times_url).content.decode("utf-8")

    trips_reader = csv.DictReader(StringIO(trips_csv))
    stop_times_reader = csv.DictReader(StringIO(stop_times_csv))
    
    # Make the imports
    import_stib_lines(route_response)
    import_stib_stops(stop_response)
    import_trips(trips_reader, stop_times_reader)

if __name__ == "__main__":    
    if "--tec" in sys.argv:
        tec_import.import_tec_gtfs(clean=True)
    elif "--stib" in sys.argv:
        import_stib_gtfs()
    else:
        get_all_incoming_buses_export()
        import_stib_gtfs()
        

    
