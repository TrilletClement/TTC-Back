#!/usr/bin/env python3
"""
TEC GTFS importer — static + realtime (legacy vehicle-positions poller).

Static GTFS is sourced from the Belgian Mobility Commons API:
  https://opendata-discovery-gtfs-static.api.production.belgianmobility.io/api/gtfs/feed/tec/static

Auth: bmc-partner-key header (same key as STIB on the BMC portal).
"""

if __name__ == "__main__":
    import sys, os
    BASE_DIR    = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
    FASTAPI_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
    sys.path.insert(0, BASE_DIR)
    sys.path.insert(0, FASTAPI_DIR)

import csv
import hashlib
import io
import os
import sys
import time
import zipfile
import requests
from collections import defaultdict
from datetime import datetime, timedelta
from io import BytesIO, StringIO

import sqlalchemy as sa
from google.transit import gtfs_realtime_pb2

from app.orm_models.db import get_db
from app.orm_models.gtfs import Agency, Line, Stop, Trip, TripStop
from app.orm_models.raw_gtfs import RawGtfsServiceDate, RawGtfsStopTime, RawGtfsTrip

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BMC_API_BASE  = "https://opendata-discovery-gtfs-static.api.production.belgianmobility.io"
GTFS_ZIP_URL  = f"{BMC_API_BASE}/api/gtfs/feed/tec/static"

BMC_API_KEY   = os.environ.get("BMC_API_KEY", "").strip()
BMC_HEADERS   = {"bmc-partner-key": BMC_API_KEY} if BMC_API_KEY else {}
print(f"[tec_import] BMC_API_KEY={'***' + BMC_API_KEY[-4:] if len(BMC_API_KEY) > 4 else '(empty — anonymous)'}")

# Legacy vehicle-positions feed (kept for backward compatibility while the
# new TripUpdates-based interval system is validated).
REALTIME_URL  = "https://gtfsrt.tectime.be/proto/RealTime/vehicles"
TEC_API_KEY   = os.environ.get("TEC_API_KEY", "").strip()

AGENCY_NAME   = "TEC"
BATCH_SIZE    = 5000
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


def _parse_seconds(time_str: str):
    """Convert GTFS HH:MM:SS (may exceed 24 h) to integer seconds from midnight."""
    if not time_str:
        return None
    try:
        h, m, s = time_str.strip().split(":")
        return int(h) * 3600 + int(m) * 60 + int(s)
    except (ValueError, AttributeError):
        return None


def _open_stop_times(zip_bytes: bytes):
    """Open stop_times.txt from in-memory zip for streaming; returns a csv.DictReader."""
    zf  = zipfile.ZipFile(BytesIO(zip_bytes))
    raw = zf.open("stop_times.txt")
    return csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8")), zf


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

def _fetch_gtfs_zip() -> tuple[dict[str, str], bytes]:
    """Download GTFS ZIP.

    Returns (text_files_dict, raw_zip_bytes).
    stop_times.txt is intentionally excluded from the dict — it is very large
    (300-500 MB uncompressed) and must be streamed from zip_bytes instead.
    """
    print(f"[{time.strftime('%H:%M:%S')}] Téléchargement GTFS statique TEC…")
    response = requests.get(GTFS_ZIP_URL, headers=BMC_HEADERS, timeout=120)
    if response.status_code != 200:
        raise RuntimeError(f"GTFS static HTTP {response.status_code}: {response.text[:200]}")

    result = {}
    with zipfile.ZipFile(BytesIO(response.content)) as zf:
        for name in ("agency.txt", "routes.txt", "stops.txt", "trips.txt",
                     "calendar.txt", "calendar_dates.txt"):
            if name in zf.namelist():
                result[name] = zf.read(name).decode("utf-8")
            else:
                print(f"  AVERTISSEMENT: {name} absent du ZIP GTFS")

    print(f"  Téléchargé ({len(response.content)/1024/1024:.1f} MB)")
    return result, response.content


# ---------------------------------------------------------------------------
# GTFS static import
# ---------------------------------------------------------------------------

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
            if not short_name:
                skipped += 1
                continue
            combo = (short_name, long_name)
            if route_id in existing_lines:
                line = existing_lines[route_id]
                for attr, val in [("short_name", short_name), ("long_name", long_name),
                                   ("route_type", route_type)]:
                    if getattr(line, attr) != val:
                        setattr(line, attr, val)
                seen_combos.add(combo)
                updated += 1
            elif combo in seen_combos:
                skipped += 1
            else:
                to_add.append(Line(route_id=route_id, short_name=short_name, long_name=long_name,
                                   route_type=route_type, agency_name=AGENCY_NAME))
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


def import_tec_calendar(calendar_csv_text: str, calendar_dates_csv_text: str):
    """
    Expand calendar.txt (weekly recurrence) + calendar_dates.txt (exceptions)
    into a flat raw_gtfs_service_date table: one row per (service_id, date).
    """
    tic = time.time()
    WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

    dates: dict[str, set[str]] = defaultdict(set)

    # Weekly recurrence
    for row in csv.DictReader(StringIO(calendar_csv_text)):
        service_id = row["service_id"]
        start = datetime.strptime(row["start_date"], "%Y%m%d")
        end   = datetime.strptime(row["end_date"],   "%Y%m%d")
        d = start
        while d <= end:
            if row[WEEKDAYS[d.weekday()]] == "1":
                dates[service_id].add(d.strftime("%Y%m%d"))
            d += timedelta(days=1)

    # Exceptions (1 = added, 2 = removed)
    for row in csv.DictReader(StringIO(calendar_dates_csv_text)):
        service_id = row["service_id"]
        date       = row["date"]
        if row["exception_type"] == "1":
            dates[service_id].add(date)
        elif row["exception_type"] == "2":
            dates[service_id].discard(date)

    session = next(get_db())
    try:
        get_tec_agency(session)
        session.execute(
            sa.text("DELETE FROM raw_gtfs_service_date WHERE agency_name = :a"),
            {"a": AGENCY_NAME},
        )
        rows = [
            {"service_id": sid, "agency_name": AGENCY_NAME, "date": d}
            for sid, day_set in dates.items()
            for d in day_set
        ]
        for batch in _chunked(rows, BATCH_SIZE):
            session.bulk_insert_mappings(RawGtfsServiceDate, batch)
        session.commit()
        print(f"TEC Calendar imported in {time.time()-tic:.2f}s "
              f"({len(dates)} services, {len(rows)} date rows)")
    finally:
        session.close()


def import_trips(trips_csv_text: str, zip_bytes: bytes):
    """
    Build canonical Trip / TripStop patterns and populate raw_gtfs_trip +
    raw_gtfs_stop_time using two streaming passes over stop_times.txt.

    Pass 1 — build ordered stop-ID lists per trip (for signatures and
             TripStop creation).  No arrival/departure times stored.
    Pass 2 — stream stop_times.txt a second time to insert raw_gtfs_stop_time
             rows in batches of BATCH_SIZE, never materialising the full list.

    Peak memory is dominated by trip_stops_ordered (~150 MB for TEC) instead
    of the old stop_times_by_trip + st_rows approach (~4-5 GB).
    """
    tic = time.time()

    # ── Parse trips.txt ───────────────────────────────────────────────────────
    t0 = time.time()
    trip_data: dict[str, dict] = {}
    for row in csv.DictReader(StringIO(trips_csv_text)):
        trip_data[row["trip_id"]] = {
            "route_id":      row.get("route_id", ""),
            "service_id":    row.get("service_id", ""),
            "dir":           int(row.get("direction_id", 0)),
            "shape_id":      row.get("shape_id") or None,
            "trip_headsign": row.get("trip_headsign") or None,
        }
    print(f"  trips.txt parsed ({len(trip_data)} trips) in {time.time()-t0:.2f}s")

    # ── Pass 1: stream stop_times.txt — ordered stop IDs only ────────────────
    # We store only (sequence, stop_id) per trip — no arrival/departure data.
    t0 = time.time()
    trip_stops_ordered: dict[str, list[tuple[int, str]]] = defaultdict(list)
    reader, zf = _open_stop_times(zip_bytes)
    try:
        for row in reader:
            tid = row["trip_id"]
            if tid in trip_data:
                trip_stops_ordered[tid].append((int(row["stop_sequence"]), row["stop_id"]))
    finally:
        zf.close()
    for tid in trip_stops_ordered:
        trip_stops_ordered[tid].sort(key=lambda x: x[0])
    row_count = sum(len(v) for v in trip_stops_ordered.values())
    print(f"  stop_times.txt pass 1 ({row_count} rows) in {time.time()-t0:.2f}s")

    # ── DB phase ──────────────────────────────────────────────────────────────
    session = next(get_db())
    try:
        route_to_line  = {l.route_id: l.id for l in session.query(Line).filter_by(agency_name=AGENCY_NAME)}
        existing_raw   = {r.gtfs_trip_id for r in
                          session.query(RawGtfsTrip.gtfs_trip_id)
                          .filter_by(agency_name=AGENCY_NAME)}
        sig_to_trip_id = {
            t.signature: t.id
            for t in session.query(Trip.id, Trip.signature).filter_by(line_agency_name=AGENCY_NAME)
        }

        new_trips_to_create: dict[str, Trip] = {}
        raw_trips_to_add: list[tuple[str, str, dict]] = []
        sig_counts: dict[str, int] = defaultdict(int)

        for g_id, info in trip_data.items():
            l_id  = route_to_line.get(info["route_id"])
            stops = trip_stops_ordered.get(g_id)
            if not l_id or not stops:
                continue
            ordered_stop_ids = [s[1] for s in stops]
            sig = _build_signature(l_id, info["dir"], ordered_stop_ids)
            sig_counts[sig] += 1

            if sig not in sig_to_trip_id and sig not in new_trips_to_create:
                new_trips_to_create[sig] = Trip(
                    line_id=l_id, line_agency_name=AGENCY_NAME,
                    direction=info["dir"], signature=sig,
                    start_stop_id=ordered_stop_ids[0], terminus_stop_id=ordered_stop_ids[-1],
                    start_agency_name=AGENCY_NAME, terminus_agency_name=AGENCY_NAME,
                )

            if g_id not in existing_raw:
                raw_trips_to_add.append((g_id, sig, info))

        # ── Flush new canonical Trips and TripStops ───────────────────────────
        t0 = time.time()
        if new_trips_to_create:
            session.add_all(new_trips_to_create.values())
            session.flush()
            ts_to_insert = []
            for sig, trip in new_trips_to_create.items():
                sig_to_trip_id[sig] = trip.id
                sample_g_id = next(g for g, s, _ in raw_trips_to_add if s == sig)
                for idx, (_, stop_id) in enumerate(trip_stops_ordered[sample_g_id]):
                    ts_to_insert.append({
                        "trip_id": trip.id, "stop_stop_id": stop_id,
                        "stop_agency_name": AGENCY_NAME, "sequence": idx,
                    })
            for batch in _chunked(ts_to_insert, BATCH_SIZE):
                session.bulk_insert_mappings(TripStop, batch)
        print(f"  canonical Trips/TripStops flushed ({len(new_trips_to_create)} new) in {time.time()-t0:.2f}s")

        # ── Update trip_count ─────────────────────────────────────────────────
        session.bulk_update_mappings(Trip, [
            {"id": sig_to_trip_id[s], "trip_count": c}
            for s, c in sig_counts.items() if s in sig_to_trip_id
        ])

        # ── best_trip_0 / best_trip_1 per line ───────────────────────────────
        t0 = time.time()
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
        print(f"  best trips updated in {time.time()-t0:.2f}s")

        # ── raw_gtfs_trip rows ────────────────────────────────────────────────
        t0 = time.time()
        session.execute(
            sa.text("""
                DELETE FROM raw_gtfs_stop_time
                WHERE raw_trip_id IN (
                    SELECT id FROM raw_gtfs_trip WHERE agency_name = :a
                )
            """),
            {"a": AGENCY_NAME},
        )
        session.execute(
            sa.text("DELETE FROM raw_gtfs_trip WHERE agency_name = :a"),
            {"a": AGENCY_NAME},
        )
        session.flush()
        print(f"  old raw rows deleted in {time.time()-t0:.2f}s")

        t0 = time.time()
        raw_trip_rows = []
        for g_id, sig, info in raw_trips_to_add:
            raw_trip_rows.append({
                "gtfs_trip_id":      g_id,
                "agency_name":       AGENCY_NAME,
                "route_id":          info["route_id"],
                "service_id":        info["service_id"],
                "direction_id":      info["dir"],
                "shape_id":          info["shape_id"],
                "trip_headsign":     info["trip_headsign"],
                "canonical_trip_id": sig_to_trip_id.get(sig),
            })
        for g_id, info in trip_data.items():
            if g_id not in existing_raw:
                continue
            l_id  = route_to_line.get(info["route_id"])
            stops = trip_stops_ordered.get(g_id)
            if not l_id or not stops:
                continue
            ordered_stop_ids = [s[1] for s in stops]
            sig = _build_signature(l_id, info["dir"], ordered_stop_ids)
            raw_trip_rows.append({
                "gtfs_trip_id":      g_id,
                "agency_name":       AGENCY_NAME,
                "route_id":          info["route_id"],
                "service_id":        info["service_id"],
                "direction_id":      info["dir"],
                "shape_id":          info["shape_id"],
                "trip_headsign":     info["trip_headsign"],
                "canonical_trip_id": sig_to_trip_id.get(sig),
            })

        for batch in _chunked(raw_trip_rows, BATCH_SIZE):
            session.bulk_insert_mappings(RawGtfsTrip, batch)
        session.flush()
        print(f"  raw_gtfs_trip inserted ({len(raw_trip_rows)} rows) in {time.time()-t0:.2f}s")

        # trip_stops_ordered is no longer needed — free it before the next heavy phase
        del trip_stops_ordered

        # ── Build lookup dicts for Pass 2 ─────────────────────────────────────
        t0 = time.time()
        gtfs_id_to_raw_pk: dict[str, int] = {}
        gtfs_id_to_canonical: dict[str, int] = {}
        for r in session.query(RawGtfsTrip.gtfs_trip_id, RawGtfsTrip.id, RawGtfsTrip.canonical_trip_id) \
                         .filter_by(agency_name=AGENCY_NAME):
            gtfs_id_to_raw_pk[r.gtfs_trip_id] = r.id
            if r.canonical_trip_id is not None:
                gtfs_id_to_canonical[r.gtfs_trip_id] = r.canonical_trip_id
        print(f"  raw_trip_id map built ({len(gtfs_id_to_raw_pk)} entries) in {time.time()-t0:.2f}s")

        t0 = time.time()
        canonical_ids = set(gtfs_id_to_canonical.values())
        trip_stop_map: dict[tuple[int, str], int] = {
            (ts.trip_id, ts.stop_stop_id): ts.id
            for ts in session.query(TripStop.id, TripStop.trip_id, TripStop.stop_stop_id)
                              .filter(TripStop.trip_id.in_(canonical_ids))
        }
        print(f"  trip_stop map built ({len(trip_stop_map)} entries) in {time.time()-t0:.2f}s")

        # ── Pass 2: stream stop_times.txt → raw_gtfs_stop_time ───────────────
        # Rows are inserted in BATCH_SIZE chunks; no full list is ever built.
        t0 = time.time()
        mapped   = 0
        inserted = 0
        batch: list[dict] = []
        reader, zf = _open_stop_times(zip_bytes)
        try:
            for row in reader:
                trip_id = row["trip_id"]
                raw_pk  = gtfs_id_to_raw_pk.get(trip_id)
                if raw_pk is None:
                    continue
                canonical_trip_id = gtfs_id_to_canonical.get(trip_id)
                stop_id = row["stop_id"]
                ts_id   = trip_stop_map.get((canonical_trip_id, stop_id)) if canonical_trip_id else None
                if ts_id:
                    mapped += 1
                batch.append({
                    "raw_trip_id":            raw_pk,
                    "stop_sequence":          int(row["stop_sequence"]),
                    "stop_id":                stop_id,
                    "arrival_seconds":        _parse_seconds(row.get("arrival_time", "")),
                    "departure_seconds":      _parse_seconds(row.get("departure_time", "")),
                    "canonical_trip_stop_id": ts_id,
                })
                if len(batch) >= BATCH_SIZE:
                    session.bulk_insert_mappings(RawGtfsStopTime, batch)
                    session.flush()
                    inserted += len(batch)
                    batch = []
        finally:
            zf.close()
        if batch:
            session.bulk_insert_mappings(RawGtfsStopTime, batch)
            inserted += len(batch)
        print(f"  raw_gtfs_stop_time inserted ({inserted} rows, {mapped} mapped) in {time.time()-t0:.2f}s")

        t0 = time.time()
        session.commit()
        print(f"  committed in {time.time()-t0:.2f}s")
        print(f"TEC Trips importés en {time.time()-tic:.2f}s")

        from app.routines.refresh_intervals import refresh_active_intervals
        refresh_active_intervals()
    finally:
        session.close()


def import_tec_gtfs():
    gtfs, zip_bytes = _fetch_gtfs_zip()
    if "routes.txt" in gtfs:    import_tec_lines(gtfs["routes.txt"])
    if "stops.txt"  in gtfs:    import_tec_stops(gtfs["stops.txt"])
    if "calendar.txt" in gtfs or "calendar_dates.txt" in gtfs:
        import_tec_calendar(
            gtfs.get("calendar.txt", ""),
            gtfs.get("calendar_dates.txt", ""),
        )
    if "trips.txt" in gtfs:
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            if "stop_times.txt" in zf.namelist():
                import_trips(gtfs["trips.txt"], zip_bytes)


# ---------------------------------------------------------------------------
# Calcul des service_ids actifs aujourd'hui  (still used by legacy RT cache)
# ---------------------------------------------------------------------------

def _active_service_ids_today(gtfs: dict) -> set:
    today       = datetime.now()
    today_str   = today.strftime("%Y%m%d")
    weekday_col = today.strftime("%A").lower()

    active = set()

    if "calendar.txt" in gtfs:
        reader = csv.DictReader(StringIO(gtfs["calendar.txt"]))
        for row in reader:
            start = row.get("start_date", "")
            end   = row.get("end_date", "")
            if start <= today_str <= end and row.get(weekday_col, "0") == "1":
                active.add(row["service_id"])

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
# Real-time — legacy vehicle-positions cache
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
    Build the legacy (stop_sequence → TripStop) cache for vehicle-positions RT.

    stop_times.txt is streamed from the ZIP bytes rather than loaded as a
    full string to avoid holding hundreds of MB in RAM.
    """
    now = time.time()
    if _TEC_RT_CACHE["seq_map"] is not None and now - _TEC_RT_CACHE["loaded_at"] < _TEC_RT_CACHE_TTL:
        return _TEC_RT_CACHE["seq_map"], _TEC_RT_CACHE["next_map"]

    print(f"[{time.strftime('%H:%M:%S')}] Chargement cache RT TEC (tous les trips du jour)…")
    tic = time.time()

    try:
        gtfs, zip_bytes = _fetch_gtfs_zip()
    except Exception as e:
        print(f"  ERREUR fetch GTFS pour cache RT : {e}")
        return _TEC_RT_CACHE.get("seq_map") or {}, _TEC_RT_CACHE.get("next_map") or {}

    active_services = _active_service_ids_today(gtfs)
    if not active_services:
        print("  ERREUR: aucun service_id actif trouvé.")
        return {}, {}

    trips_reader = csv.DictReader(StringIO(gtfs["trips.txt"]))
    active_gtfs_trip_ids = {}
    for row in trips_reader:
        if row.get("service_id") in active_services:
            active_gtfs_trip_ids[row["trip_id"]] = (
                row["route_id"],
                int(row.get("direction_id", 0)),
            )

    print(f"  GTFS trips actifs aujourd'hui : {len(active_gtfs_trip_ids)}")
    if not active_gtfs_trip_ids:
        return {}, {}

    # Resolve gtfs_trip_id → canonical_trip_id via raw_gtfs_trip
    gtfs_to_internal = {}
    gtfs_ids_list    = list(active_gtfs_trip_ids.keys())
    for batch in _chunked(gtfs_ids_list, BATCH_SIZE):
        rows = session.execute(
            sa.text("""
                SELECT gtfs_trip_id, canonical_trip_id
                FROM raw_gtfs_trip
                WHERE gtfs_trip_id = ANY(:ids)
                  AND agency_name  = :agency
                  AND canonical_trip_id IS NOT NULL
            """),
            {"ids": batch, "agency": AGENCY_NAME},
        ).all()
        for row in rows:
            gtfs_to_internal[row.gtfs_trip_id] = row.canonical_trip_id

    print(f"  GTFS trips résolus en internal trip_id : {len(gtfs_to_internal)}")

    internal_trip_meta = {}
    for gtfs_trip_id, internal_trip_id in gtfs_to_internal.items():
        if gtfs_trip_id in active_gtfs_trip_ids:
            internal_trip_meta[internal_trip_id] = active_gtfs_trip_ids[gtfs_trip_id]

    if not internal_trip_meta:
        print("  ERREUR: aucun internal_trip_id résolu.")
        return {}, {}

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

    # Stream stop_times.txt — only keep sequences for active trips
    print(f"  Parsing stop_times.txt pour aligner les séquences…")
    active_set = set(active_gtfs_trip_ids.keys())
    gtfs_trip_sequences: dict[str, list[int]] = defaultdict(list)
    reader, zf = _open_stop_times(zip_bytes)
    try:
        for row in reader:
            if row["trip_id"] in active_set:
                gtfs_trip_sequences[row["trip_id"]].append(int(row["stop_sequence"]))
    finally:
        zf.close()

    gtfs_trip_id_to_rank_to_gtfs_seq = {}
    for gtfs_trip_id, seqs in gtfs_trip_sequences.items():
        sorted_seqs = sorted(seqs)
        gtfs_trip_id_to_rank_to_gtfs_seq[gtfs_trip_id] = {
            rank: gtfs_seq for rank, gtfs_seq in enumerate(sorted_seqs)
        }

    internal_to_gtfs_trip = {}
    for gtfs_trip_id, internal_trip_id in gtfs_to_internal.items():
        if internal_trip_id not in internal_to_gtfs_trip:
            internal_to_gtfs_trip[internal_trip_id] = gtfs_trip_id

    seq_map  = {}
    next_map = {}
    skipped_no_meta = skipped_no_gtfs = skipped_no_seq = 0

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
        if key not in seq_map:
            seq_map[key] = row.ts_id
        if row.next_ts_id:
            next_map[row.ts_id] = row.next_ts_id

    _TEC_RT_CACHE.update({"seq_map": seq_map, "next_map": next_map, "loaded_at": now})
    print(f"  Cache chargé en {time.time()-tic:.2f}s — seq_map: {len(seq_map)}, next_map: {len(next_map)}")
    if skipped_no_meta or skipped_no_gtfs or skipped_no_seq:
        print(f"  Skipped: no_meta={skipped_no_meta} no_gtfs={skipped_no_gtfs} no_seq={skipped_no_seq}")
    return seq_map, next_map


def get_all_incoming_buses_tec():
    tic = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] Démarrage mise à jour Temps Réel TEC (legacy)…")

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
                if v.current_status == 1:   # STOPPED_AT → mark current + next
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
