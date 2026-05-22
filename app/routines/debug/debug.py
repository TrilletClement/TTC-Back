#!/usr/bin/env python3
"""
Diagnostic TEC — Ligne 6
Récupère le feed RT et affiche tout ce qui concerne la ligne 6.
"""

import csv
import hashlib
import os
import time
import zipfile
import requests
from collections import defaultdict
from io import BytesIO, StringIO

from google.transit import gtfs_realtime_pb2

TEC_API_KEY  = os.environ.get("TEC_API_KEY", "36497DD5F3AD4262B24981633E73EF33")
REALTIME_URL = "https://gtfsrt.tectime.be/proto/RealTime/vehicles"
GTFS_ZIP_URL = "https://opendata.tec-wl.be/Current%20GTFS/TEC-GTFS.zip"

TARGET_LINE  = "6"   # short_name dans routes.txt


# ── 1. Feed RT ──────────────────────────────────────────────────────────────

def fetch_rt_feed():
    print(f"\n[1] Récupération feed RT → {REALTIME_URL}")
    params   = {"key": TEC_API_KEY}
    response = requests.get(REALTIME_URL, params=params, timeout=15)
    print(f"    HTTP {response.status_code}  ({len(response.content)} bytes)")
    if response.status_code != 200:
        raise RuntimeError(response.text[:300])
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(response.content)
    return feed


def inspect_rt_feed(feed):
    entities = [e for e in feed.entity if e.HasField("vehicle")]
    print(f"    Total véhicules dans le feed : {len(entities)}")

    # Toutes les route_ids présentes
    route_ids = sorted({e.vehicle.trip.route_id for e in entities})
    print(f"    Échantillon route_ids ({len(route_ids)} uniques) : {route_ids[:30]}")

    # Filtre "6" de plusieurs façons
    candidates = []
    for e in entities:
        v = e.vehicle
        rid = v.trip.route_id
        if rid == TARGET_LINE or rid.endswith(f"-{TARGET_LINE}") or TARGET_LINE in rid.split("-"):
            candidates.append(v)

    print(f"\n    Véhicules avec route_id contenant '{TARGET_LINE}' : {len(candidates)}")
    for v in candidates[:20]:
        print(f"      route_id={v.trip.route_id!r:30s}  dir={v.trip.direction_id}  "
              f"trip_id={v.trip.trip_id!r:20s}  seq={v.current_stop_sequence}  "
              f"status={v.current_status}")

    return route_ids


# ── 2. GTFS statique ────────────────────────────────────────────────────────

def fetch_gtfs_zip():
    print(f"\n[2] Téléchargement GTFS statique…")
    headers  = {"User-Agent": "Mozilla/5.0 (compatible; Python requests)"}
    response = requests.get(GTFS_ZIP_URL, headers=headers, timeout=120)
    print(f"    HTTP {response.status_code}  ({len(response.content)/1024/1024:.1f} MB)")
    if response.status_code != 200:
        raise RuntimeError(response.text[:300])
    result = {}
    with zipfile.ZipFile(BytesIO(response.content)) as zf:
        for name in ("routes.txt", "trips.txt", "stop_times.txt"):
            if name in zf.namelist():
                result[name] = zf.read(name).decode("utf-8")
    return result


def inspect_gtfs_ligne6(gtfs):
    # ── routes.txt
    routes_reader = csv.DictReader(StringIO(gtfs["routes.txt"]))
    ligne6_routes = [r for r in routes_reader if r.get("route_short_name") == TARGET_LINE]
    print(f"\n    Lignes avec short_name='{TARGET_LINE}' dans routes.txt : {len(ligne6_routes)}")
    for r in ligne6_routes:
        print(f"      route_id={r['route_id']!r:30s}  long={r.get('route_long_name')!r}")

    if not ligne6_routes:
        print("    ⚠  Aucune route trouvée — vérifier le short_name exact.")
        # Afficher les 30 premiers short_names pour aider
        routes_reader2 = csv.DictReader(StringIO(gtfs["routes.txt"]))
        names = sorted({r.get("route_short_name","") for r in routes_reader2})
        print(f"    Short names disponibles (50 premiers) : {names[:50]}")
        return []

    target_route_ids = {r["route_id"] for r in ligne6_routes}
    print(f"    route_ids ciblés : {target_route_ids}")

    # ── trips.txt
    trips_reader = csv.DictReader(StringIO(gtfs["trips.txt"]))
    ligne6_trips = [t for t in trips_reader if t["route_id"] in target_route_ids]
    print(f"    Trips pour la ligne 6 : {len(ligne6_trips)}")

    dir_counts = defaultdict(int)
    for t in ligne6_trips:
        dir_counts[t.get("direction_id", "?")] += 1
    print(f"    Répartition par direction : {dict(dir_counts)}")

    if ligne6_trips:
        sample = ligne6_trips[:3]
        print(f"    Exemple trips : {[t['trip_id'] for t in sample]}")

    # ── stop_times pour un trip exemple
    if ligne6_trips:
        sample_trip_id = ligne6_trips[0]["trip_id"]
        print(f"\n    Stop_times du trip exemple '{sample_trip_id}' :")
        st_reader = csv.DictReader(StringIO(gtfs["stop_times.txt"]))
        stop_times = [r for r in st_reader if r["trip_id"] == sample_trip_id]
        stop_times.sort(key=lambda r: int(r["stop_sequence"]))
        for st in stop_times:
            print(f"      seq={st['stop_sequence']:4s}  stop_id={st['stop_id']!r:20s}  "
                  f"arrival={st.get('arrival_time')}  departure={st.get('departure_time')}")

    return list(target_route_ids)


# ── 3. Croisement RT ↔ GTFS ─────────────────────────────────────────────────

def cross_check(feed, gtfs_route_ids, all_rt_route_ids):
    print(f"\n[3] Croisement RT ↔ GTFS")
    print(f"    route_ids GTFS pour ligne 6 : {gtfs_route_ids}")

    entities = [e for e in feed.entity if e.HasField("vehicle")]
    matched = [e.vehicle for e in entities if e.vehicle.trip.route_id in set(gtfs_route_ids)]
    print(f"    Véhicules RT matchant ces route_ids : {len(matched)}")
    for v in matched[:20]:
        print(f"      route_id={v.trip.route_id!r}  dir={v.trip.direction_id}  "
              f"seq={v.current_stop_sequence}  status={v.current_status}  "
              f"trip_id={v.trip.trip_id!r}")

    # Vérifier si les route_ids GTFS apparaissent du tout dans le RT
    missing = [rid for rid in gtfs_route_ids if rid not in set(all_rt_route_ids)]
    if missing:
        print(f"\n    ⚠  Ces route_ids GTFS sont ABSENTS du feed RT : {missing}")
        # Chercher des route_ids RT qui ressemblent
        for rid in missing:
            similar = [r for r in all_rt_route_ids if rid in r or r in rid]
            if similar:
                print(f"      route_id GTFS '{rid}' → similaires dans RT : {similar[:5]}")


# ── main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print(f"  Diagnostic TEC — Ligne {TARGET_LINE}")
    print("=" * 60)

    feed          = fetch_rt_feed()
    all_rt_routes = inspect_rt_feed(feed)

    gtfs          = fetch_gtfs_zip()
    gtfs_routes   = inspect_gtfs_ligne6(gtfs)

    cross_check(feed, gtfs_routes, all_rt_routes)

    print("\n" + "=" * 60)
    print("  Fin du diagnostic")
    print("=" * 60)