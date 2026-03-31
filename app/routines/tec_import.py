#!/usr/bin/env python3
"""
TEC GTFS Importer v2.1 — RT matching par stop_id réel + logique statut fine.

Changements vs v1 :
  - Import statique : TripStop.sequence stocke maintenant la VRAIE séquence
    GTFS (depuis stop_times.txt) au lieu d'un idx réindexé (0,1,2…).
  - Cache RT : reconstruit autour de deux lookups :
      (trip_id, stop_sequence) → stop_id        [depuis stop_times en mémoire]
      (route_id, direction, stop_id) → [ts_ids] [depuis DB, tous les TripStops]
  - Matching RT : pour chaque bus, on retrouve le stop_id réel via son
    trip_id + current_stop_sequence, puis on allume TOUS les TripStops
    de cette (ligne, direction, stop_id) — pas seulement ceux du best_trip.
  - best_trip reste figé après création de la board (template layout uniquement).
"""

if __name__ == "__main__":
    import sys, os
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../'))
    sys.path.insert(0, BASE_DIR)
    FASTAPI_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
    sys.path.insert(0, FASTAPI_DIR)

import csv
import hashlib
import os
import sys
import time
import zipfile
import requests
from collections import defaultdict
from io import BytesIO, StringIO

import sqlalchemy as sa
from google.transit import gtfs_realtime_pb2

from app.orm_models.db import get_db
from app.orm_models.gtfs import Agency, GTFSTrip, Line, Stop, SubAgency, Trip, TripStop

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GTFS_ZIP_URL = "https://opendata.tec-wl.be/Current%20GTFS/TEC-GTFS.zip"
TEC_API_KEY  = os.environ.get("TEC_API_KEY", "36497DD5F3AD4262B24981633E73EF33")
REALTIME_URL = "https://gtfsrt.tectime.be/proto/RealTime/vehicles"
AGENCY_NAME  = "TEC"
BATCH_SIZE   = 5000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_signature(line_id: int, direction: int, stop_ids: list) -> str:
    payload = f"{line_id}:{direction}|" + "|".join(stop_ids)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _chunked(iterable, size):
    chunk = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def get_tec_agency(session):
    agency = session.query(Agency).filter_by(name=AGENCY_NAME).first()
    if not agency:
        agency = Agency(name=AGENCY_NAME, country="Belgium")
        session.add(agency)
        session.commit()
    return agency


# ---------------------------------------------------------------------------
# GTFS static download
# ---------------------------------------------------------------------------

def _fetch_gtfs_zip() -> dict:
    print(f"[{time.strftime('%H:%M:%S')}] Téléchargement GTFS statique TEC…")
    headers  = {"User-Agent": "Mozilla/5.0 (compatible; Python requests)"}
    response = requests.get(GTFS_ZIP_URL, headers=headers, timeout=120)
    if response.status_code != 200:
        raise RuntimeError(f"GTFS static HTTP {response.status_code}: {response.text[:200]}")

    result = {}
    with zipfile.ZipFile(BytesIO(response.content)) as zf:
        for name in ("agency.txt", "routes.txt", "stops.txt", "trips.txt", "stop_times.txt"):
            if name in zf.namelist():
                result[name] = zf.read(name).decode("utf-8")
            else:
                print(f"  AVERTISSEMENT: {name} absent du ZIP GTFS")

    print(f"  Téléchargé ({len(response.content)/1024/1024:.1f} MB)")
    return result


# ---------------------------------------------------------------------------
# GTFS static import
# ---------------------------------------------------------------------------

def import_tec_agency(agency_csv_text: str):
    tic     = time.time()
    reader  = csv.DictReader(StringIO(agency_csv_text))
    session = next(get_db())
    try:
        get_tec_agency(session)
        existing = {s.id: s for s in session.query(SubAgency).filter_by(agency_name=AGENCY_NAME)}
        to_add, updated = [], 0
        for row in reader:
            sub_id, sub_name = row.get("agency_id"), row.get("agency_name")
            if not sub_id or not sub_name:
                continue
            if sub_id in existing:
                if existing[sub_id].name != sub_name:
                    existing[sub_id].name = sub_name
                    updated += 1
            else:
                to_add.append(SubAgency(id=sub_id, name=sub_name, agency_name=AGENCY_NAME))
        if to_add:
            session.bulk_save_objects(to_add)
        session.commit()
        print(f"TEC SubAgencies updated in {time.time()-tic:.2f}s (added {len(to_add)}, updated {updated})")
    finally:
        session.close()


def import_tec_lines(routes_csv_text: str):
    tic     = time.time()
    reader  = csv.DictReader(StringIO(routes_csv_text))
    session = next(get_db())
    try:
        get_tec_agency(session)
        existing_lines = {l.route_id: l for l in session.query(Line).filter_by(agency_name=AGENCY_NAME)}
        seen_combos    = {(l.short_name, l.long_name) for l in existing_lines.values()}
        to_add, updated, skipped = [], 0, 0
        for row in reader:
            route_id     = row.get("route_id")
            short_name   = row.get("route_short_name")
            long_name    = row.get("route_long_name")
            route_type   = row.get("route_type")
            subagency_id = row.get("agency_id")
            if not short_name:
                skipped += 1
                continue
            combo = (short_name, long_name)
            if route_id in existing_lines:
                line = existing_lines[route_id]
                for attr, val in [("short_name", short_name), ("long_name", long_name),
                                   ("route_type", route_type), ("subagency_id", subagency_id)]:
                    if getattr(line, attr) != val:
                        setattr(line, attr, val)
                seen_combos.add(combo)
                updated += 1
            elif combo in seen_combos:
                skipped += 1
            else:
                to_add.append(Line(route_id=route_id, short_name=short_name, long_name=long_name,
                                   route_type=route_type, agency_name=AGENCY_NAME, subagency_id=subagency_id))
                seen_combos.add(combo)
        if to_add:
            session.bulk_save_objects(to_add)
        session.commit()
        print(f"TEC Lines updated in {time.time()-tic:.2f}s (added {len(to_add)}, updated {updated}, skipped {skipped})")
    finally:
        session.close()


def import_tec_stops(stops_csv_text: str):
    tic     = time.time()
    reader  = csv.DictReader(StringIO(stops_csv_text))
    session = next(get_db())
    try:
        get_tec_agency(session)
        existing = {s.stop_id: s for s in session.query(Stop).filter_by(agency_name=AGENCY_NAME)}
        to_add, updated = [], 0
        for row in reader:
            stop_id, stop_name = row.get("stop_id"), row.get("stop_name")
            if not stop_id:
                continue
            if stop_id in existing:
                if existing[stop_id].name != stop_name:
                    existing[stop_id].name = stop_name
                    updated += 1
            else:
                to_add.append(Stop(stop_id=stop_id, name=stop_name, agency_name=AGENCY_NAME))
        if to_add:
            session.bulk_save_objects(to_add)
        session.commit()
        print(f"TEC Stops updated in {time.time()-tic:.2f}s (added {len(to_add)}, updated {updated})")
    finally:
        session.close()


def import_trips(trips_reader, stop_times_reader):
    """
    Import des trips et TripStops.

    FIX v2 : TripStop.sequence stocke maintenant la vraie séquence GTFS
    (ex: 1, 2, 3… ou 1, 3, 5…) au lieu d'un idx réindexé (0, 1, 2…).

    C'est critique pour le matching RT : le feed envoie current_stop_sequence
    qui correspond directement à stop_times.stop_sequence, pas à un idx.
    """
    tic = time.time()

    trip_data = {
        row["trip_id"]: {"route_id": row["route_id"], "dir": int(row.get("direction_id", 0)), "stops": []}
        for row in trips_reader
    }
    for row in stop_times_reader:
        if row["trip_id"] in trip_data:
            trip_data[row["trip_id"]]["stops"].append((int(row["stop_sequence"]), row["stop_id"]))

    session = next(get_db())
    try:
        route_to_line       = {l.route_id: l.id for l in session.query(Line).filter_by(agency_name=AGENCY_NAME)}
        existing_gtfs_trips = {gt.id for gt in session.query(GTFSTrip.id)}
        sig_to_trip_id      = {
            t.signature: t.id
            for t in session.query(Trip.id, Trip.signature).filter_by(line_agency_name=AGENCY_NAME)
        }

        new_trips_to_create  = {}
        gtfs_mappings_to_add = []
        sig_counts           = defaultdict(int)

        for g_id, info in trip_data.items():
            l_id = route_to_line.get(info["route_id"])
            if not l_id or not info["stops"]:
                continue
            ordered_stops = [s[1] for s in sorted(info["stops"])]
            sig = _build_signature(l_id, info["dir"], ordered_stops)
            sig_counts[sig] += 1
            if g_id not in existing_gtfs_trips:
                if sig not in sig_to_trip_id and sig not in new_trips_to_create:
                    new_trips_to_create[sig] = Trip(
                        line_id=l_id, line_agency_name=AGENCY_NAME,
                        direction=info["dir"], signature=sig,
                        start_stop_id=ordered_stops[0],
                        terminus_stop_id=ordered_stops[-1],
                        start_agency_name=AGENCY_NAME, terminus_agency_name=AGENCY_NAME,
                    )
                gtfs_mappings_to_add.append((g_id, sig))

        if new_trips_to_create:
            session.add_all(new_trips_to_create.values())
            session.flush()
            ts_to_insert = []
            for sig, trip in new_trips_to_create.items():
                sig_to_trip_id[sig] = trip.id
                sample_gtfs_id = next(g for g, s in gtfs_mappings_to_add if s == sig)
                for real_seq, s_id in sorted(trip_data[sample_gtfs_id]["stops"]):
                    ts_to_insert.append({
                        "trip_id": trip.id,
                        "stop_stop_id": s_id,
                        "stop_agency_name": AGENCY_NAME,
                        "sequence": real_seq,  # FIX v2 : vraie séquence GTFS, pas idx
                    })
            for batch in _chunked(ts_to_insert, BATCH_SIZE):
                session.bulk_insert_mappings(TripStop, batch)

        if gtfs_mappings_to_add:
            seen, rows = set(), []
            for g_id, sig in gtfs_mappings_to_add:
                if g_id not in seen and sig in sig_to_trip_id:
                    seen.add(g_id)
                    rows.append({"id": g_id, "trip_id": sig_to_trip_id[sig]})
            for batch in _chunked(rows, BATCH_SIZE):
                session.bulk_insert_mappings(GTFSTrip, batch)

        session.bulk_update_mappings(Trip, [
            {"id": sig_to_trip_id[s], "trip_count": c}
            for s, c in sig_counts.items() if s in sig_to_trip_id
        ])

        # Sélection du best_trip — inchangée volontairement.
        # Le best_trip sert UNIQUEMENT de template pour le layout de la board.
        # Il ne doit pas changer après création de la board.
        # Le matching RT n'utilise plus best_trip (voir _load_tec_rt_cache v2).
        best_trips_query = session.query(
            Trip.line_id, Trip.direction, Trip.id,
            (sa.func.max(TripStop.sequence) * Trip.trip_count).label("score"),
        ).join(TripStop).filter(Trip.line_agency_name == AGENCY_NAME).group_by(Trip.id).subquery()

        for line in session.query(Line).filter_by(agency_name=AGENCY_NAME).all():
            for d in [0, 1]:
                # Ne mettre à jour best_trip que si pas encore défini
                # (protège le layout des boards existantes)
                if getattr(line, f"best_trip_{d}_id") is not None:
                    continue
                best = session.query(best_trips_query.c.id).filter(
                    best_trips_query.c.line_id == line.id,
                    best_trips_query.c.direction == d,
                ).order_by(best_trips_query.c.score.desc()).first()
                if best:
                    setattr(line, f"best_trip_{d}_id", best.id)

        session.commit()
        print(f"TEC Trips importés en {time.time()-tic:.2f}s")
    finally:
        session.close()


def import_tec_gtfs():
    gtfs = _fetch_gtfs_zip()
    if "agency.txt"   in gtfs: import_tec_agency(gtfs["agency.txt"])
    if "routes.txt"   in gtfs: import_tec_lines(gtfs["routes.txt"])
    if "stops.txt"    in gtfs: import_tec_stops(gtfs["stops.txt"])
    if "trips.txt" in gtfs and "stop_times.txt" in gtfs:
        import_trips(
            csv.DictReader(StringIO(gtfs["trips.txt"])),
            csv.DictReader(StringIO(gtfs["stop_times.txt"])),
        )


# ---------------------------------------------------------------------------
# Cache RT v2
#
# Structure du nouveau cache (chargé en mémoire, TTL 10 min) :
#
#   stop_seq_cache :
#     (trip_id, stop_sequence) → stop_id
#     Construit depuis stop_times.txt en mémoire.
#     Permet de retrouver le stop_id réel depuis ce que le feed RT envoie.
#
#   ts_map :
#     (route_id, direction, stop_id) → [ts_id1, ts_id2, ...]
#     Construit depuis la DB : TOUS les TripStops de chaque (ligne, direction, stop).
#     Permet d'allumer tous les boards concernés, peu importe le trip actif.
#
#   next_map :
#     ts_id → ts_id_suivant
#     Inchangé : pour marquer le prochain arrêt quand le bus est STOPPED_AT.
# ---------------------------------------------------------------------------
_TEC_EMPTY_MATCHES = 0
_TEC_RT_CACHE_TTL  = 600
_TEC_RT_CACHE      = {
    "stop_seq_cache": None,  # (trip_id, seq) → stop_id
    "ts_map": None,          # (route_id, direction, stop_id) → [ts_ids]
    "next_map": None,        # ts_id → next_ts_id
    "loaded_at": 0.0,
}


def _fetch_vehicle_positions_tec():
    params   = {"key": TEC_API_KEY} if TEC_API_KEY else None
    response = requests.get(REALTIME_URL, params=params, timeout=10)
    if response.status_code != 200:
        raise RuntimeError(f"TEC RT HTTP {response.status_code}: {response.text[:200]}")
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(response.content)
    return feed


def _build_stop_seq_cache(stop_times_text: str) -> dict:
    """
    Charge stop_times.txt en mémoire et construit le lookup :
      (trip_id, stop_sequence) → stop_id

    ~6M lignes pour TEC, ~300-400MB RAM.
    Appelé une seule fois au premier chargement du cache RT.
    """
    print(f"  Chargement stop_times en mémoire…")
    tic    = time.time()
    cache  = {}
    reader = csv.DictReader(StringIO(stop_times_text))
    for row in reader:
        cache[(row["trip_id"], int(row["stop_sequence"]))] = row["stop_id"]
    print(f"  stop_seq_cache : {len(cache)} entrées en {time.time()-tic:.2f}s")
    return cache


# Cache du stop_times en mémoire — chargé une seule fois, pas de TTL
# (le GTFS statique ne change que lors d'un import explicite)
_STOP_SEQ_CACHE = None


def _ensure_stop_seq_cache() -> dict:
    """
    Charge stop_times depuis internet si pas encore en mémoire.
    Après le premier chargement, reste en mémoire jusqu'au redémarrage du process.
    """
    global _STOP_SEQ_CACHE
    if _STOP_SEQ_CACHE is not None:
        return _STOP_SEQ_CACHE

    print(f"[{time.strftime('%H:%M:%S')}] Premier chargement stop_seq_cache…")
    # On télécharge uniquement stop_times.txt et trips.txt pour le cache RT
    headers  = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(GTFS_ZIP_URL, headers=headers, timeout=120)
    if response.status_code != 200:
        raise RuntimeError(f"GTFS zip HTTP {response.status_code}")

    with zipfile.ZipFile(BytesIO(response.content)) as zf:
        stop_times_text = zf.read("stop_times.txt").decode("utf-8")

    _STOP_SEQ_CACHE = _build_stop_seq_cache(stop_times_text)
    return _STOP_SEQ_CACHE


def _load_tec_rt_cache(session):
    """
    Construit le cache RT v2.

    Différence clé vs v1 :
      v1 : seq_map[(route_id, direction, sequence)] = ts_id_du_best_trip
           → un seul TripStop par (route, dir, seq), uniquement celui du best_trip

      v2 : ts_map[(route_id, direction, stop_id)] = [ts_id1, ts_id2, ...]
           → TOUS les TripStops de toutes les lignes+directions qui passent
             par ce stop_id physique
    """
    now = time.time()
    if _TEC_RT_CACHE["ts_map"] and now - _TEC_RT_CACHE["loaded_at"] < _TEC_RT_CACHE_TTL:
        return (
            _TEC_RT_CACHE["stop_seq_cache"],
            _TEC_RT_CACHE["ts_map"],
            _TEC_RT_CACHE["next_map"],
        )

    print(f"[{time.strftime('%H:%M:%S')}] Chargement cache RT TEC v2…")
    tic = time.time()

    # 1. S'assurer que stop_times est en mémoire
    stop_seq_cache = _ensure_stop_seq_cache()

    # 2. Charger depuis la DB TOUS les TripStops TEC avec leur stop_id et
    #    le route_id de leur ligne — pas seulement les best_trips.
    #
    #    On récupère aussi le next_ts_id via LEAD() pour le marquage STOPPED_AT.
    rows = session.execute(
        sa.text("""
            SELECT
                ts.id                AS ts_id,
                ts.trip_id           AS trip_id,
                ts.stop_stop_id      AS stop_id,
                l.route_id           AS route_id,
                t.direction          AS direction,
                LEAD(ts.id) OVER (
                    PARTITION BY ts.trip_id
                    ORDER BY ts.sequence
                )                    AS next_ts_id
            FROM trip_stop ts
            JOIN trip t      ON t.id = ts.trip_id
            JOIN line l      ON l.id = t.line_id
            WHERE ts.stop_agency_name = :agency
              AND t.line_agency_name  = :agency
              AND l.agency_name       = :agency
            ORDER BY ts.trip_id, ts.sequence
        """),
        {"agency": AGENCY_NAME},
    ).all()

    # 3. Construire ts_map et next_map
    ts_map   = defaultdict(list)  # (route_id, direction, stop_id) → [ts_ids]
    next_map = {}                 # ts_id → next_ts_id

    for row in rows:
        key = (row.route_id, row.direction, row.stop_id)
        ts_map[key].append(row.ts_id)
        if row.next_ts_id:
            next_map[row.ts_id] = row.next_ts_id

    n_keys    = len(ts_map)
    n_ts_ids  = sum(len(v) for v in ts_map.values())

    _TEC_RT_CACHE.update({
        "stop_seq_cache": stop_seq_cache,
        "ts_map":         dict(ts_map),
        "next_map":       next_map,
        "loaded_at":      now,
    })

    print(f"  Cache chargé en {time.time()-tic:.2f}s : "
          f"{n_keys} clés (route+dir+stop) → {n_ts_ids} ts_ids")
    return stop_seq_cache, dict(ts_map), next_map


def get_all_incoming_buses_tec():
    """
    Mise à jour RT v2.

    Pour chaque bus dans le feed :
      1. trip_id + current_stop_sequence
              ↓ stop_seq_cache
      2. stop_id réel
              ↓ ts_map
      3. tous les ts_ids de (route_id, direction, stop_id)
              ↓
      4. vehicle_incoming = true sur tous ces TripStops
    """
    tic = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] Démarrage mise à jour Temps Réel TEC v2.1…")

    try:
        feed     = _fetch_vehicle_positions_tec()
        entities = [e for e in feed.entity if e.HasField("vehicle")]
        print(f"  Feed reçu : {len(entities)} véhicules")

        if not entities:
            print("  Aucune donnée RT reçue, mise à jour ignorée.")
            return

        session = next(get_db())
        try:
            stop_seq_cache, ts_map, next_map = _load_tec_rt_cache(session)

            if not ts_map:
                print("  Cache RT vide, mise à jour annulée.")
                return

            incoming_ids  = set()
            matched       = 0
            no_seq        = 0   # bus sans current_stop_sequence
            no_stop_id    = 0   # trip_id+seq absent du stop_seq_cache
            no_map        = 0   # (route_id, dir, stop_id) absent du ts_map
            status_counts = defaultdict(int)

            for entity in entities:
                v         = entity.vehicle
                route_id  = v.trip.route_id
                direction = v.trip.direction_id
                trip_id   = v.trip.trip_id
                stop_seq  = v.current_stop_sequence
                status_counts[v.current_status] += 1

                if not stop_seq:
                    no_seq += 1
                    continue

                # Étape 1 : retrouver le stop_id réel depuis trip_id + séquence
                stop_id = stop_seq_cache.get((trip_id, stop_seq))
                if stop_id is None:
                    no_stop_id += 1
                    continue

                # Étape 2 : trouver tous les TripStops de ce (route, dir, stop)
                ts_ids = ts_map.get((route_id, direction, stop_id))
                if not ts_ids:
                    no_map += 1
                    continue

                matched += 1
                status = v.current_status

                for ts_id in ts_ids:
                    next_id = next_map.get(ts_id)
                    if status == 1:
                        # STOPPED_AT : bus à l'arrêt → allumer cet arrêt + le suivant
                        # (il va repartir dans quelques secondes)
                        incoming_ids.add(ts_id)
                        if next_id:
                            incoming_ids.add(next_id)
                    else:
                        # INCOMING_AT (0) ou IN_TRANSIT_TO (2) : bus en route vers cet arrêt
                        # → allumer uniquement le suivant dans la séquence board
                        # Si c'est le dernier arrêt (pas de suivant), allumer quand même
                        if next_id:
                            incoming_ids.add(next_id)
                        else:
                            incoming_ids.add(ts_id)

            print(f"  Statuts : {dict(status_counts)}  (0=INCOMING_AT, 1=STOPPED_AT, 2=IN_TRANSIT_TO)")
            print(f"  Matched: {matched} | sans séquence: {no_seq} "
                  f"| stop_id inconnu: {no_stop_id} | hors ts_map: {no_map}")

            # Diagnostic : afficher un échantillon des cas non matchés
            if no_stop_id > 0:
                shown = 0
                for entity in entities:
                    v = entity.vehicle
                    if v.current_stop_sequence and \
                       stop_seq_cache.get((v.trip.trip_id, v.current_stop_sequence)) is None:
                        print(f"  [STOP_ID INCONNU] trip_id={v.trip.trip_id} "
                              f"seq={v.current_stop_sequence} route={v.trip.route_id}")
                        shown += 1
                        if shown >= 5:
                            break

            if no_map > 0:
                shown = 0
                for entity in entities:
                    v       = entity.vehicle
                    stop_id = stop_seq_cache.get((v.trip.trip_id, v.current_stop_sequence))
                    key     = (v.trip.route_id, v.trip.direction_id, stop_id)
                    if stop_id and key not in ts_map:
                        print(f"  [HORS TS_MAP] route={v.trip.route_id} "
                              f"dir={v.trip.direction_id} stop_id={stop_id} "
                              f"trip_id={v.trip.trip_id}")
                        shown += 1
                        if shown >= 5:
                            break

            global _TEC_EMPTY_MATCHES
            if matched == 0:
                _TEC_EMPTY_MATCHES += 1
                if _TEC_EMPTY_MATCHES < 3:
                    print(f"  Aucune position appariée (#{_TEC_EMPTY_MATCHES}/3), mise à jour ignorée.")
                    return
                print("  Aucune position appariée (x3), reset forcé.")
            else:
                _TEC_EMPTY_MATCHES = 0

            # Reset global puis marquage des bus actifs
            session.execute(
                sa.text("UPDATE trip_stop SET vehicle_incoming = false WHERE stop_agency_name = 'TEC'")
            )
            if incoming_ids:
                for batch in _chunked(list(incoming_ids), BATCH_SIZE):
                    session.execute(
                        sa.text("UPDATE trip_stop SET vehicle_incoming = true WHERE id = ANY(:ids)"),
                        {"ids": batch},
                    )
            session.commit()

        finally:
            session.close()

        print(f"  Résultat : {len(incoming_ids)} TripStops marqués 'incoming'.")
        print(f"  Update TEC RT terminée en {time.time()-tic:.2f}s")

    except Exception as e:
        print(f"ERREUR CRITIQUE RT TEC: {e}")
        import traceback
        traceback.print_exc()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "--tec-rt" in sys.argv:
        print("Lancement mise à jour Temps Réel TEC v2.1…")
        get_all_incoming_buses_tec()
    else:
        import_tec_gtfs()