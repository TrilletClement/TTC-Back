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
from app.orm_models.db import get_db
from app.orm_models.gtfs import Agency, GTFSTrip, Line, Stop, Trip, TripStop
import json
import csv
import time
import re
from io import StringIO
from collections import defaultdict
import os
import sys
from app.routines import tec_import
from app.routines.missed_bus_store import get_stib_missed_bus_store

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
    
    session = next(get_db())
    try:
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
    finally:
        session.close()

def import_stib_stops(response):
    tic = time.time()
    reader = csv.DictReader(StringIO(response.content.decode('utf-8')))
    session = next(get_db())
    try:
        get_stib_agency(session)
        for row in reader:
            sid, name = row.get("stop_id"), row.get("stop_name")
            if not sid: continue
            stop = session.query(Stop).filter_by(stop_id=sid, agency_name="STIB").first()
            if stop: stop.name = name
            else: session.add(Stop(stop_id=sid, name=name, agency_name="STIB"))
        session.commit()
        print(f"STIB Stops updated in {time.time() - tic:.2f}s")
    finally:
        session.close()
    
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

    session = next(get_db())
    try:
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
    finally:
        session.close()

def normalize_stib_id(stop_id):
    digits = re.sub(r'[A-Z]+$', '', str(stop_id))
    if len(digits) < 4:
        digits = digits.zfill(4)
    return digits
        
_STIB_TS_CACHE = {
    "ts_map": None,
    "line_map": None,
    "stops_base4": None,
    "terminus_by_line": None,
    "loaded_at": 0.0,
}
_STIB_EMPTY_MATCHES = 0


def _base4_stib_id(value):
    digits = re.sub(r"[^0-9]", "", str(value))
    return digits[:4].zfill(4) if digits else ""


def _load_stib_tripstop_cache(session, ttl_seconds=600):
    now = time.time()
    if _STIB_TS_CACHE["ts_map"] and now - _STIB_TS_CACHE["loaded_at"] < ttl_seconds:
        return (
            _STIB_TS_CACHE["line_map"],
            _STIB_TS_CACHE["ts_map"],
            _STIB_TS_CACHE["stops_base4"],
            _STIB_TS_CACHE["terminus_by_line"],
        )

    line_map = defaultdict(list)
    for line_id, short_name in session.query(Line.id, Line.short_name).filter_by(agency_name="STIB"):
        line_map[short_name].append(line_id)

    stops_base4 = set()
    for (stop_id,) in session.query(Stop.stop_id).filter_by(agency_name="STIB").all():
        b = _base4_stib_id(stop_id)
        if b:
            stops_base4.add(b)

    terminus_by_line = defaultdict(set)
    for line_id, terminus_id in session.query(Trip.line_id, Trip.terminus_stop_id).filter_by(line_agency_name="STIB"):
        b = _base4_stib_id(terminus_id)
        if b:
            terminus_by_line[line_id].add(b)

    rows = session.execute(
        sa.text(
            """
            SELECT
                ts.id AS ts_id,
                ts.stop_stop_id AS stop_id,
                t.line_id AS line_id,
                t.terminus_stop_id AS terminus_id,
                LEAD(ts.id) OVER (PARTITION BY ts.trip_id ORDER BY ts.sequence) AS next_ts_id
            FROM trip_stop ts
            JOIN trip t ON t.id = ts.trip_id
            WHERE t.line_agency_name = :agency
            """
        ),
        {"agency": "STIB"},
    ).all()

    ts_map = defaultdict(list)
    for row in rows:
        base_term = _base4_stib_id(row.terminus_id)
        base_stop = _base4_stib_id(row.stop_id)
        key = (row.line_id, base_term, base_stop)
        ts_map[key].append((row.ts_id, row.next_ts_id))

    _STIB_TS_CACHE["line_map"] = line_map
    _STIB_TS_CACHE["ts_map"] = ts_map
    _STIB_TS_CACHE["stops_base4"] = stops_base4
    _STIB_TS_CACHE["terminus_by_line"] = terminus_by_line
    _STIB_TS_CACHE["loaded_at"] = now
    return line_map, ts_map, stops_base4, terminus_by_line


def get_all_incoming_buses_export():
    tic = time.time()
    export_url = "https://data.stib-mivb.brussels/api/explore/v2.1/catalog/datasets/vehicle-position-rt-production/exports/json"

    print(f"[{time.strftime('%H:%M:%S')}] Démarrage mise à jour Temps Réel STIB (fast)...")

    try:
        response = requests.get(export_url, headers=STIB_HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"ERREUR API: Code {response.status_code}")
            return

        data = response.json()
        if not data:
            print("Aucune donnée RT reçue, mise à jour ignorée.")
            return

        missed = get_stib_missed_bus_store()
        now_ts = time.time()

        incoming_ids = set()
        matched_positions = 0

        session = next(get_db())
        try:
            line_map, ts_map, stops_base4, terminus_by_line = _load_stib_tripstop_cache(session)

            for entry in data:
                l_short = entry.get("lineid")
                l_ids = line_map.get(l_short)
                if not l_ids:
                    # Unknown line in DB (not in GTFS routes)
                    continue

                v_pos = entry.get("vehiclepositions")
                if isinstance(v_pos, str):
                    v_pos = json.loads(v_pos)

                for pos in v_pos:
                    raw_dir = _base4_stib_id(pos.get("directionId"))
                    # NOTE: do NOT apply any local terminus mapping here; we want to surface
                    # raw mismatches to report them upstream to STIB.
                    t_id = raw_dir
                    s_id = _base4_stib_id(pos.get("pointId"))

                    sample = {
                        "line": l_short,
                        "terminus_raw": pos.get("directionId"),
                        "terminus": t_id,
                        "stop_raw": pos.get("pointId"),
                        "stop": s_id,
                        "distanceFromPoint": pos.get("distanceFromPoint"),
                    }

                    # (1) direction/terminus not in GTFS stops
                    if t_id and t_id not in stops_base4:
                        missed.record(
                            "direction_not_in_gtfs",
                            line=l_short,
                            terminus=t_id,
                            stop=s_id or "????",
                            sample=sample,
                            seen_at=now_ts,
                        )
                        continue

                    # (2) realtime stop not in GTFS stops
                    if s_id and s_id not in stops_base4:
                        missed.record(
                            "stop_not_in_gtfs",
                            line=l_short,
                            terminus=t_id or "????",
                            stop=s_id,
                            sample=sample,
                            seen_at=now_ts,
                        )
                        continue

                    # (3) line + terminus matches no trip
                    if t_id and not any(t_id in terminus_by_line.get(lid, set()) for lid in l_ids):
                        missed.record(
                            "no_trips",
                            line=l_short,
                            terminus=t_id,
                            stop=s_id or "????",
                            sample=sample,
                            seen_at=now_ts,
                        )
                        continue

                    for lid in l_ids:
                        key = (lid, t_id, s_id)
                        matches = ts_map.get(key)
                        if not matches:
                            continue
                        for tsid, next_id in matches:
                            if pos.get("distanceFromPoint") in ("0", 0):
                                incoming_ids.add(tsid)
                            else:
                                if next_id:
                                    incoming_ids.add(next_id)
                        matched_positions += 1

                    # (4) line + terminus + stop matches no trip_stop
                    if t_id and s_id and not any(ts_map.get((lid, t_id, s_id)) for lid in l_ids):
                        missed.record(
                            "no_tripstop",
                            line=l_short,
                            terminus=t_id,
                            stop=s_id,
                            sample=sample,
                            seen_at=now_ts,
                        )

            global _STIB_EMPTY_MATCHES
            if matched_positions == 0:
                _STIB_EMPTY_MATCHES += 1
                if _STIB_EMPTY_MATCHES < 3:
                    print("Aucune position appariée, mise à jour ignorée.")
                    return
                print("Aucune position appariée (x3), reset incoming.")
            else:
                _STIB_EMPTY_MATCHES = 0

            session.execute(
                sa.text("UPDATE trip_stop SET vehicle_incoming = false WHERE stop_agency_name = 'STIB'")
            )
            if incoming_ids:
                session.execute(
                    sa.text("UPDATE trip_stop SET vehicle_incoming = true WHERE id = ANY(:ids)"),
                    {"ids": list(incoming_ids)},
                )
            session.commit()
        finally:
            session.close()

        missed.flush()

        print(f"Résultat: {len(incoming_ids)} TripStops marqués 'incoming'.")
        print(f"Update STIB RT (fast) terminée en {time.time() - tic:.2f}s")

    except Exception as e:
        print(f"ERREUR CRITIQUE RT (fast): {e}")
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
    elif "--stib-rt" in sys.argv:
        print("Lancement mise à jour Temps Réel STIB (rapide)...")
        #get_all_incoming_buses_export_fast()
        #get_all_incoming_buses_export_fast()
        #get_all_incoming_buses_export_fast()
    else:
        get_all_incoming_buses_export()
        import_stib_gtfs()
        

    

