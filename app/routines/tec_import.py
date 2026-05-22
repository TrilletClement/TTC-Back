#!/usr/bin/env python3
"""
TEC GTFS Importer — aligned with STIB importer structure.
RT matching via tous les trips actifs du jour (calendar + calendar_dates).
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
from datetime import datetime
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

BATCH_SIZE      = 5000
TRIP_BATCH_SIZE = 1000


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
        for name in ("agency.txt", "routes.txt", "stops.txt", "trips.txt",
                     "stop_times.txt", "calendar.txt", "calendar_dates.txt"):
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
                        start_stop_id=ordered_stops[0], terminus_stop_id=ordered_stops[-1],
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
                for idx, (_, s_id) in enumerate(sorted(trip_data[sample_gtfs_id]["stops"])):
                    ts_to_insert.append({"trip_id": trip.id, "stop_stop_id": s_id,
                                         "stop_agency_name": AGENCY_NAME, "sequence": idx})
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

        best_trips_query = session.query(
            Trip.line_id, Trip.direction, Trip.id,
            (sa.func.max(TripStop.sequence) * Trip.trip_count).label("score"),
        ).join(TripStop).filter(Trip.line_agency_name == AGENCY_NAME).group_by(Trip.id).subquery()

        for line in session.query(Line).filter_by(agency_name=AGENCY_NAME).all():
            for d in [0, 1]:
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
    if "agency.txt"    in gtfs: import_tec_agency(gtfs["agency.txt"])
    if "routes.txt"    in gtfs: import_tec_lines(gtfs["routes.txt"])
    if "stops.txt"     in gtfs: import_tec_stops(gtfs["stops.txt"])
    if "trips.txt" in gtfs and "stop_times.txt" in gtfs:
        import_trips(
            csv.DictReader(StringIO(gtfs["trips.txt"])),
            csv.DictReader(StringIO(gtfs["stop_times.txt"])),
        )


# ---------------------------------------------------------------------------
# Calcul des service_ids actifs aujourd'hui
# ---------------------------------------------------------------------------

def _active_service_ids_today(gtfs: dict) -> set:
    """
    Retourne l'ensemble des service_ids actifs aujourd'hui
    en combinant calendar.txt et calendar_dates.txt.
    """
    today       = datetime.now()
    today_str   = today.strftime("%Y%m%d")          # ex: "20250521"
    weekday_col = today.strftime("%A").lower()       # ex: "thursday"

    active = set()

    # ── calendar.txt : services récurrents ──────────────────────────────────
    if "calendar.txt" in gtfs:
        reader = csv.DictReader(StringIO(gtfs["calendar.txt"]))
        for row in reader:
            start = row.get("start_date", "")
            end   = row.get("end_date", "")
            if start <= today_str <= end and row.get(weekday_col, "0") == "1":
                active.add(row["service_id"])

    # ── calendar_dates.txt : exceptions (added=1, removed=2) ────────────────
    if "calendar_dates.txt" in gtfs:
        reader = csv.DictReader(StringIO(gtfs["calendar_dates.txt"]))
        for row in reader:
            if row.get("date") != today_str:
                continue
            if row.get("exception_type") == "1":
                active.add(row["service_id"])
            elif row.get("exception_type") == "2":
                active.discard(row["service_id"])

    print(f"  service_ids actifs aujourd'hui ({today_str}, {weekday_col}) : {len(active)}")
    return active


# ---------------------------------------------------------------------------
# Real-time — cache module-level
# ---------------------------------------------------------------------------
_TEC_EMPTY_MATCHES = 0
_TEC_RT_CACHE_TTL  = 600
_TEC_RT_CACHE      = {"seq_map": None, "next_map": None, "loaded_at": 0.0}


def _fetch_vehicle_positions_tec():
    params   = {"key": TEC_API_KEY} if TEC_API_KEY else None
    response = requests.get(REALTIME_URL, params=params, timeout=10)
    if response.status_code != 200:
        raise RuntimeError(f"TEC RT HTTP {response.status_code}: {response.text[:200]}")
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(response.content)
    return feed


def _load_tec_rt_cache(session):
    """
    Charge dans le cache tous les trips actifs aujourd'hui
    (via calendar + calendar_dates), pas seulement les best_trips.

    Structure du cache :
      seq_map  : (route_id, direction, stop_sequence) → ts_id
      next_map : ts_id → ts_id_suivant
    """
    now = time.time()
    if _TEC_RT_CACHE["seq_map"] is not None and now - _TEC_RT_CACHE["loaded_at"] < _TEC_RT_CACHE_TTL:
        return _TEC_RT_CACHE["seq_map"], _TEC_RT_CACHE["next_map"]

    print(f"[{time.strftime('%H:%M:%S')}] Chargement cache RT TEC (tous les trips du jour)…")
    tic = time.time()

    # ── 1. Récupérer le GTFS statique pour connaître les service_ids du jour ─
    try:
        gtfs = _fetch_gtfs_zip()
    except Exception as e:
        print(f"  ERREUR fetch GTFS pour cache RT : {e}")
        return _TEC_RT_CACHE.get("seq_map") or {}, _TEC_RT_CACHE.get("next_map") or {}

    active_services = _active_service_ids_today(gtfs)
    if not active_services:
        print("  ERREUR: aucun service_id actif trouvé.")
        return {}, {}

    # ── 2. trips.txt → trip_id actifs du jour avec leur route_id & direction ─
    trips_reader = csv.DictReader(StringIO(gtfs["trips.txt"]))
    active_gtfs_trip_ids = {}   # gtfs_trip_id → (route_id, direction_id)
    for row in trips_reader:
        if row.get("service_id") in active_services:
            active_gtfs_trip_ids[row["trip_id"]] = (
                row["route_id"],
                int(row.get("direction_id", 0)),
            )

    print(f"  GTFS trips actifs aujourd'hui : {len(active_gtfs_trip_ids)}")
    if not active_gtfs_trip_ids:
        print("  ERREUR: aucun trip GTFS actif aujourd'hui.")
        return {}, {}

    # ── 3. Résoudre gtfs_trip_id → internal trip_id via GTFSTrip ────────────
    #    On fait ça en batches pour ne pas exploser la requête SQL
    gtfs_to_internal = {}   # gtfs_trip_id → internal_trip_id
    gtfs_ids_list    = list(active_gtfs_trip_ids.keys())

    for batch in _chunked(gtfs_ids_list, BATCH_SIZE):
        rows = session.execute(
            sa.text("SELECT id, trip_id FROM gtfs_trip WHERE id = ANY(:ids)"),
            {"ids": batch},
        ).all()
        for row in rows:
            gtfs_to_internal[row.id] = row.trip_id

    print(f"  GTFS trips résolus en internal trip_id : {len(gtfs_to_internal)}")

    # ── 4. internal_trip_id → (route_id, direction) ─────────────────────────
    #    On construit le mapping depuis les données GTFS (plus fiable que la DB)
    internal_trip_meta = {}  # internal_trip_id → (route_id, direction)
    for gtfs_trip_id, internal_trip_id in gtfs_to_internal.items():
        if gtfs_trip_id in active_gtfs_trip_ids:
            internal_trip_meta[internal_trip_id] = active_gtfs_trip_ids[gtfs_trip_id]

    if not internal_trip_meta:
        print("  ERREUR: aucun internal_trip_id résolu.")
        return {}, {}

    # ── 5. Charger les TripStops pour tous ces trips ─────────────────────────
    #    On utilise la sequence GTFS originale (depuis stop_times.txt)
    #    plutôt que celle stockée en DB qui est réindexée 0,1,2…
    #
    #    Problème : notre DB stocke sequence=0,1,2… mais le feed RT envoie
    #    la stop_sequence originale du GTFS (ex: 1,2,3… ou 10,20,30…).
    #    → On doit reconstruire le mapping depuis stop_times.txt.

    # Construire stop_sequence GTFS → ts_id pour chaque trip actif
    # D'abord, charger les TripStops depuis la DB pour avoir les ts_id
    internal_trip_ids = list(internal_trip_meta.keys())

    print(f"  Chargement TripStops DB pour {len(internal_trip_ids)} trips…")
    db_rows = []
    for batch in _chunked(internal_trip_ids, BATCH_SIZE):
        rows = session.execute(
            sa.text("""
                SELECT
                    ts.id       AS ts_id,
                    ts.trip_id  AS trip_id,
                    ts.sequence AS db_sequence,
                    LEAD(ts.id) OVER (PARTITION BY ts.trip_id ORDER BY ts.sequence) AS next_ts_id
                FROM trip_stop ts
                WHERE ts.trip_id = ANY(:trip_ids)
                  AND ts.stop_agency_name = :agency
                ORDER BY ts.trip_id, ts.sequence
            """),
            {"trip_ids": batch, "agency": AGENCY_NAME},
        ).all()
        db_rows.extend(rows)

    # db_sequence est 0-indexed dans notre DB, mais le feed RT utilise
    # la stop_sequence GTFS (1-indexed ou autre).
    # On doit aligner les deux.
    #
    # Stratégie : parser stop_times.txt pour les trips actifs
    # et construire db_sequence (rank 0,1,2…) → gtfs_sequence.

    print(f"  Parsing stop_times.txt pour aligner les séquences…")
    # gtfs_trip_id → liste triée de (gtfs_stop_sequence, stop_id)
    gtfs_trip_sequences = defaultdict(list)
    st_reader = csv.DictReader(StringIO(gtfs["stop_times.txt"]))
    active_set = set(active_gtfs_trip_ids.keys())
    for row in st_reader:
        if row["trip_id"] in active_set:
            gtfs_trip_sequences[row["trip_id"]].append(int(row["stop_sequence"]))

    # Pour chaque gtfs_trip_id actif → mapping db_sequence(rank) → gtfs_sequence
    # db_sequence = index dans la liste triée par gtfs_sequence
    gtfs_trip_id_to_rank_to_gtfs_seq = {}
    for gtfs_trip_id, seqs in gtfs_trip_sequences.items():
        sorted_seqs = sorted(seqs)
        gtfs_trip_id_to_rank_to_gtfs_seq[gtfs_trip_id] = {
            rank: gtfs_seq for rank, gtfs_seq in enumerate(sorted_seqs)
        }

    # internal_trip_id → gtfs_trip_id (premier trouvé suffit, les variants
    # du même trip interne partagent la même séquence d'arrêts)
    internal_to_gtfs_trip = {}
    for gtfs_trip_id, internal_trip_id in gtfs_to_internal.items():
        if internal_trip_id not in internal_to_gtfs_trip:
            internal_to_gtfs_trip[internal_trip_id] = gtfs_trip_id

    # ── 6. Construire seq_map et next_map ────────────────────────────────────
    seq_map  = {}   # (route_id, direction, gtfs_stop_sequence) → ts_id
    next_map = {}   # ts_id → ts_id_suivant

    skipped_no_meta  = 0
    skipped_no_gtfs  = 0
    skipped_no_seq   = 0

    for row in db_rows:
        meta = internal_trip_meta.get(row.trip_id)
        if not meta:
            skipped_no_meta += 1
            continue

        route_id, direction = meta
        gtfs_trip_id = internal_to_gtfs_trip.get(row.trip_id)
        if not gtfs_trip_id:
            skipped_no_gtfs += 1
            continue

        rank_map = gtfs_trip_id_to_rank_to_gtfs_seq.get(gtfs_trip_id)
        if not rank_map:
            skipped_no_seq += 1
            continue

        gtfs_seq = rank_map.get(row.db_sequence)
        if gtfs_seq is None:
            skipped_no_seq += 1
            continue

        key = (route_id, direction, gtfs_seq)
        # En cas de conflit (même clé, trip différent) : on garde le premier.
        # C'est acceptable car le feed RT ne peut matcher qu'une position à la fois.
        if key not in seq_map:
            seq_map[key] = row.ts_id

        if row.next_ts_id:
            next_map[row.ts_id] = row.next_ts_id

    _TEC_RT_CACHE.update({"seq_map": seq_map, "next_map": next_map, "loaded_at": now})

    print(f"  Cache chargé en {time.time()-tic:.2f}s")
    print(f"  seq_map: {len(seq_map)} entrées | next_map: {len(next_map)} entrées")
    if skipped_no_meta or skipped_no_gtfs or skipped_no_seq:
        print(f"  Skipped: no_meta={skipped_no_meta} no_gtfs={skipped_no_gtfs} no_seq={skipped_no_seq}")

    return seq_map, next_map


def get_all_incoming_buses_tec():
    tic = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] Démarrage mise à jour Temps Réel TEC…")

    try:
        feed = _fetch_vehicle_positions_tec()

        entities = [e for e in feed.entity if e.HasField("vehicle")]
        print(f"  Feed reçu : {len(entities)} véhicules")

        if not entities:
            print("  Aucune donnée RT reçue, mise à jour ignorée.")
            return

        session = next(get_db())
        try:
            seq_map, next_map = _load_tec_rt_cache(session)

            # Toujours reset d'abord, peu importe ce qui suit
            session.execute(
                sa.text("UPDATE trip_stop SET vehicle_incoming = false WHERE stop_agency_name = 'TEC'")
            )

            if not seq_map:
                print("  Cache RT vide, reset effectué sans marquage.")
                session.commit()
                return

            incoming_ids  = set()
            matched       = 0
            no_seq        = 0
            no_map        = 0
            status_counts = defaultdict(int)

            for entity in entities:
                v         = entity.vehicle
                route_id  = v.trip.route_id
                direction = v.trip.direction_id
                stop_seq  = v.current_stop_sequence
                status    = v.current_status
                status_counts[status] += 1

                if not stop_seq:
                    no_seq += 1
                    continue

                ts_id = seq_map.get((route_id, direction, stop_seq))
                if ts_id is None:
                    no_map += 1
                    continue

                matched += 1

                # GTFS-RT statuses :
                #   0 INCOMING_AT   → bus approche cet arrêt  → marquer ts_id
                #   1 STOPPED_AT    → bus à l'arrêt           → marquer ts_id + suivant
                #   2 IN_TRANSIT_TO → bus en route vers arrêt → marquer ts_id
                if v.current_status == 1:
                    incoming_ids.add(ts_id)
                    next_id = next_map.get(ts_id)
                    if next_id:
                        incoming_ids.add(next_id)
                else:
                    incoming_ids.add(ts_id)

            print(f"  Statuts : {dict(status_counts)}  (0=INCOMING_AT, 1=STOPPED_AT, 2=IN_TRANSIT_TO)")
            print(f"  Matched: {matched} | sans séquence: {no_seq} | hors cache: {no_map}")

            global _TEC_EMPTY_MATCHES
            if matched == 0:
                _TEC_EMPTY_MATCHES += 1
                print(f"  Aucune position appariée (#{_TEC_EMPTY_MATCHES}) — reset effectué quand même.")
                session.commit()
                return

            _TEC_EMPTY_MATCHES = 0

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
        print("Lancement mise à jour Temps Réel TEC…")
        get_all_incoming_buses_tec()
    else:
        import_tec_gtfs()