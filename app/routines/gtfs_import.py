#!/usr/bin/env python3
"""
Generic GTFS static importer + GtfsOperator base class.

Static import
─────────────
Call import_gtfs_static(agency_name, zip_bytes) for any GTFS-compliant operator.
Optional columns (route_color, etc.) are detected from CSV headers automatically.
stop_times.txt is always streamed in two passes — never fully loaded into RAM.

Operator class hierarchy
────────────────────────
Subclass GtfsOperator to add a new operator:

    class DeLijnOperator(GtfsOperator):
        AGENCY_NAME     = "DE_LIJN"
        GTFS_STATIC_URL = "https://..."
        GTFS_RT_URL     = "https://..."

        @property
        def _headers(self):
            return {"Authorization": f"Bearer {API_KEY}"}

The default parse_rt_feed() handles standard GTFS-RT VehiclePositions (protobuf).
Override it entirely in subclasses that use a non-standard feed (see StibOperator).
"""

import csv
import hashlib
import io
import time
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from io import BytesIO, StringIO

import requests
import sqlalchemy as sa
from google.transit import gtfs_realtime_pb2

from app.orm_models.db import get_db
from app.orm_models.gtfs import Agency, Line, Stop, Trip, TripStop
from app.orm_models.raw_gtfs import RawGtfsServiceDate, RawGtfsStopTime, RawGtfsTrip

BATCH_SIZE = 5000


def refresh_active_intervals() -> None:
    """Refresh the active_incoming_intervals materialized view."""
    tic = time.time()
    session = next(get_db())
    try:
        populated = session.execute(sa.text(
            "SELECT ispopulated FROM pg_matviews "
            "WHERE matviewname = 'active_incoming_intervals'"
        )).scalar()
        sql = (
            "REFRESH MATERIALIZED VIEW CONCURRENTLY active_incoming_intervals"
            if populated else
            "REFRESH MATERIALIZED VIEW active_incoming_intervals"
        )
        session.execute(sa.text(sql))
        session.commit()
        print(f"  active_incoming_intervals refreshed in {time.time()-tic:.2f}s")
    except Exception as e:
        session.rollback()
        print(f"  ERROR refreshing active_incoming_intervals: {e}")
    finally:
        session.close()


def _snapshot_led_stop_mapping(session) -> dict[int, tuple[str, str]]:
    """Capture old_trip_stop_id → (stop_id, agency_name) for all stops linked to LEDs.

    Must be called BEFORE raw_gtfs_stop_time is deleted during re-import, otherwise
    the canonical_trip_stop_id values are gone and the rebuild cannot remap broken links.
    """
    rows = session.execute(sa.text("""
        SELECT DISTINCT rst.canonical_trip_stop_id, rst.stop_id, rgt.agency_name
        FROM raw_gtfs_stop_time rst
        JOIN raw_gtfs_trip rgt ON rgt.id = rst.raw_trip_id
        WHERE rst.canonical_trip_stop_id IN (
            SELECT DISTINCT trip_stop_id FROM trip_stop_led_link
        )
    """)).all()
    return {row.canonical_trip_stop_id: (row.stop_id, row.agency_name) for row in rows}


def _rebuild_trip_stop_led_links(session, agency_name: str, snapshot: dict[int, tuple[str, str]] | None = None) -> None:
    """Répare les liens trip_stop_led_link qui pointent vers des trip_stop_id
    qui n'existent plus, en les remappant via stop_stop_id + stop_agency_name.

    Appelé après chaque import statique pour garantir la cohérence même si
    les trip_stop ont été recréés avec de nouveaux IDs (ex: après --import).
    """
    tic = time.time()

    # 1. Trouver les liens cassés (trip_stop_id inexistant)
    broken = session.execute(sa.text("""
        SELECT tsl.led_id, tsl.trip_stop_id
        FROM trip_stop_led_link tsl
        WHERE NOT EXISTS (
            SELECT 1 FROM trip_stop ts WHERE ts.id = tsl.trip_stop_id
        )
    """)).all()

    if not broken:
        print(f"  trip_stop_led_link: no broken links found")
        return

    print(f"  trip_stop_led_link: {len(broken)} broken links found, rebuilding...")

    broken_ts_ids = list({row.trip_stop_id for row in broken})

    # Use the pre-import snapshot when available (avoids querying already-replaced raw data).
    # Fall back to querying raw_gtfs_stop_time for the case where this is called without a snapshot.
    old_to_stop: dict[int, tuple[str, str]] = {}  # old_id -> (stop_stop_id, agency_name)
    if snapshot is not None:
        for ts_id in broken_ts_ids:
            if ts_id in snapshot:
                old_to_stop[ts_id] = snapshot[ts_id]
    else:
        rows = session.execute(sa.text("""
            SELECT DISTINCT rst.canonical_trip_stop_id, rst.stop_id, rgt.agency_name
            FROM raw_gtfs_stop_time rst
            JOIN raw_gtfs_trip rgt ON rgt.id = rst.raw_trip_id
            WHERE rst.canonical_trip_stop_id = ANY(:ids)
        """), {"ids": broken_ts_ids}).all()
        for row in rows:
            old_to_stop[row.canonical_trip_stop_id] = (row.stop_id, row.agency_name)

    if not old_to_stop:
        # Fallback: les anciens canonical_trip_stop_id ne sont plus dans raw_gtfs_stop_time
        # On ne peut pas reconstruire sans info supplémentaire
        print(f"  trip_stop_led_link: cannot rebuild — no stop mapping found in raw data")
        # Supprimer les liens cassés pour éviter les fantômes
        session.execute(sa.text("""
            DELETE FROM trip_stop_led_link
            WHERE NOT EXISTS (
                SELECT 1 FROM trip_stop ts WHERE ts.id = trip_stop_led_link.trip_stop_id
            )
        """))
        session.flush()
        print(f"  trip_stop_led_link: {len(broken)} broken links deleted")
        return

    # 3. Trouver les nouveaux trip_stop_id via stop_stop_id
    stop_ids_needed = list({v[0] for v in old_to_stop.values()})
    new_stop_rows = session.execute(sa.text("""
        SELECT id, stop_stop_id, stop_agency_name
        FROM trip_stop
        WHERE stop_stop_id = ANY(:ids)
          AND stop_agency_name = :a
    """), {"ids": stop_ids_needed, "a": agency_name}).all()

    # stop_stop_id -> nouveau trip_stop_id (prend le premier trouvé)
    stop_to_new_ts: dict[str, int] = {}
    for row in new_stop_rows:
        if row.stop_stop_id not in stop_to_new_ts:
            stop_to_new_ts[row.stop_stop_id] = row.id

    # 4. Reconstruire les liens
    to_insert = []
    to_delete = []
    for led_id, old_ts_id in broken:
        mapping = old_to_stop.get(old_ts_id)
        if mapping:
            stop_stop_id, _ = mapping
            new_ts_id = stop_to_new_ts.get(stop_stop_id)
            if new_ts_id:
                to_insert.append({"trip_stop_id": new_ts_id, "led_id": led_id})
            else:
                to_delete.append({"led_id": led_id, "trip_stop_id": old_ts_id})
        else:
            to_delete.append({"led_id": led_id, "trip_stop_id": old_ts_id})

    # Supprimer les liens cassés
    if to_delete:
        session.execute(sa.text("""
            DELETE FROM trip_stop_led_link
            WHERE led_id = :led_id AND trip_stop_id = :trip_stop_id
        """), to_delete)

    # Insérer les nouveaux liens
    if to_insert:
        session.execute(sa.text("""
            INSERT INTO trip_stop_led_link (trip_stop_id, led_id)
            VALUES (:trip_stop_id, :led_id)
            ON CONFLICT DO NOTHING
        """), to_insert)

    session.flush()
    print(f"  trip_stop_led_link: {len(to_insert)} rebuilt, {len(to_delete)} deleted"
          f" in {time.time()-tic:.2f}s")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

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
    if not time_str:
        return None
    try:
        h, m, s = time_str.strip().split(":")
        return int(h) * 3600 + int(m) * 60 + int(s)
    except (ValueError, AttributeError):
        return None


def _build_signature(line_id: int, direction: int, stop_ids: list) -> str:
    payload = f"{line_id}:{direction}|" + "|".join(stop_ids)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _open_stop_times(zip_bytes: bytes):
    zf  = zipfile.ZipFile(BytesIO(zip_bytes))
    raw = zf.open("stop_times.txt")
    return csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8")), zf


def load_text_files(zip_bytes: bytes) -> dict[str, str]:
    result = {}
    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        for name in ("agency.txt", "routes.txt", "stops.txt", "trips.txt",
                     "calendar.txt", "calendar_dates.txt"):
            if name in zf.namelist():
                result[name] = zf.read(name).decode("utf-8")
    return result


def _ensure_agency(session, agency_name: str, country: str = "Belgium") -> Agency:
    agency = session.query(Agency).filter_by(name=agency_name).first()
    if not agency:
        agency = Agency(name=agency_name, country=country)
        session.add(agency)
        session.commit()
    return agency


# ---------------------------------------------------------------------------
# Static import — lines, stops, calendar, trips
# ---------------------------------------------------------------------------

def _import_lines(agency_name: str, routes_csv_text: str):
    tic    = time.time()
    reader = csv.DictReader(StringIO(routes_csv_text))
    fields = reader.fieldnames or []
    has_color      = "route_color"      in fields
    has_text_color = "route_text_color" in fields

    session = next(get_db())
    try:
        _ensure_agency(session, agency_name)
        existing    = {l.route_id: l for l in session.query(Line).filter_by(agency_name=agency_name)}
        seen_combos = {(l.short_name, l.long_name) for l in existing.values()}
        to_add, updated, skipped = [], 0, 0

        for row in reader:
            route_id   = (row.get("route_id")        or "").strip()
            short_name = (row.get("route_short_name") or "").strip()
            long_name  = (row.get("route_long_name")  or "").strip()
            route_type = (row.get("route_type")       or "").strip() or None
            if not short_name:
                skipped += 1
                continue

            combo = (short_name, long_name)
            data  = {
                "route_id":    route_id or None,
                "short_name":  short_name,
                "long_name":   long_name,
                "route_type":  route_type,
                "agency_name": agency_name,
            }
            if has_color:
                raw_c = (row.get("route_color") or "000000").strip().lstrip("#")
                data["color"] = "#" + raw_c.zfill(6).upper()
            if has_text_color:
                raw_tc = (row.get("route_text_color") or "FFFFFF").strip().lstrip("#")
                data["text_color"] = "#" + raw_tc.zfill(6).upper()

            if route_id and route_id in existing:
                line = existing[route_id]
                for k, v in data.items():
                    setattr(line, k, v)
                seen_combos.add(combo)
                updated += 1
            elif combo in seen_combos:
                skipped += 1
            else:
                to_add.append(Line(**data))
                seen_combos.add(combo)

        if to_add:
            session.bulk_save_objects(to_add)
        session.commit()
        print(f"{agency_name} Lines updated in {time.time()-tic:.2f}s "
              f"(added {len(to_add)}, updated {updated}, skipped {skipped})")
    finally:
        session.close()


def _import_stops(agency_name: str, stops_csv_text: str):
    tic     = time.time()
    reader  = csv.DictReader(StringIO(stops_csv_text))
    session = next(get_db())
    try:
        _ensure_agency(session, agency_name)
        existing = {s.stop_id: s for s in session.query(Stop).filter_by(agency_name=agency_name)}
        to_add, updated = [], 0
        for row in reader:
            stop_id   = (row.get("stop_id")  or "").strip()
            stop_name = (row.get("stop_name") or "").strip()
            if not stop_id:
                continue
            if stop_id in existing:
                if existing[stop_id].name != stop_name:
                    existing[stop_id].name = stop_name
                    updated += 1
            else:
                to_add.append(Stop(stop_id=stop_id, name=stop_name, agency_name=agency_name))
        if to_add:
            session.bulk_save_objects(to_add)
        session.commit()
        print(f"{agency_name} Stops updated in {time.time()-tic:.2f}s "
              f"(added {len(to_add)}, updated {updated})")
    finally:
        session.close()


def _import_calendar(agency_name: str, calendar_csv_text: str, calendar_dates_csv_text: str):
    tic      = time.time()
    WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    dates: dict[str, set[str]] = defaultdict(set)

    if calendar_csv_text:
        for row in csv.DictReader(StringIO(calendar_csv_text)):
            sid   = row.get("service_id", "")
            start = datetime.strptime(row["start_date"], "%Y%m%d")
            end   = datetime.strptime(row["end_date"],   "%Y%m%d")
            d = start
            while d <= end:
                if row.get(WEEKDAYS[d.weekday()]) == "1":
                    dates[sid].add(d.strftime("%Y%m%d"))
                d += timedelta(days=1)

    if calendar_dates_csv_text:
        for row in csv.DictReader(StringIO(calendar_dates_csv_text)):
            sid  = row.get("service_id", "")
            date = row.get("date", "")
            if row.get("exception_type") == "1":
                dates[sid].add(date)
            elif row.get("exception_type") == "2":
                dates[sid].discard(date)

    session = next(get_db())
    try:
        session.execute(sa.text("DELETE FROM raw_gtfs_service_date WHERE agency_name = :a"), {"a": agency_name})
        rows = [
            {"service_id": sid, "agency_name": agency_name, "date": d}
            for sid, day_set in dates.items() for d in day_set
        ]
        for batch in _chunked(rows, BATCH_SIZE):
            session.bulk_insert_mappings(RawGtfsServiceDate, batch)
        session.commit()
        print(f"{agency_name} Calendar imported in {time.time()-tic:.2f}s "
              f"({len(dates)} services, {len(rows)} date rows)")
    finally:
        session.close()


def _import_trips(agency_name: str, trips_csv_text: str, zip_bytes: bytes):
    """Two-pass streaming trip import."""
    tic = time.time()

    t0 = time.time()
    trip_data: dict[str, dict] = {}
    for row in csv.DictReader(StringIO(trips_csv_text)):
        trip_data[row["trip_id"]] = {
            "route_id":      row.get("route_id", ""),
            "service_id":    row.get("service_id", ""),
            "dir": int(row.get("direction_id") or 0),
            "shape_id":      row.get("shape_id") or None,
            "trip_headsign": row.get("trip_headsign") or None,
        }
    print(f"  trips.txt parsed ({len(trip_data)} trips) in {time.time()-t0:.2f}s")

    t0 = time.time()
    session = next(get_db())
    try:
        used_stop_ids: set[str] = {
            row[0] for row in session.execute(sa.text(
                "SELECT DISTINCT stop_stop_id FROM trip_stop WHERE stop_agency_name = :a"
            ), {"a": agency_name})
        }
    finally:
        session.close()
    print(f"  {len(used_stop_ids)} stop_ids used on boards")

    if not used_stop_ids:
        print(f"  No configured stops — importing all trips (first import)")
    else:
        relevant_trip_ids: set[str] = set()
        reader, zf = _open_stop_times(zip_bytes)
        try:
            for row in reader:
                if row["trip_id"] in trip_data and row["stop_id"] in used_stop_ids:
                    relevant_trip_ids.add(row["trip_id"])
        finally:
            zf.close()
        print(f"  {len(relevant_trip_ids)} relevant trips (pass through a configured stop) "
              f"in {time.time()-t0:.2f}s")
        trip_data = {k: v for k, v in trip_data.items() if k in relevant_trip_ids}

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
    print(f"  stop_times.txt pass 1 ({sum(len(v) for v in trip_stops_ordered.values())} rows) "
          f"in {time.time()-t0:.2f}s")

    session = next(get_db())
    try:
        route_to_line  = {l.route_id: l.id for l in session.query(Line).filter_by(agency_name=agency_name)}
        sig_to_trip_id = {t.signature: t.id for t in
                          session.query(Trip.id, Trip.signature).filter_by(line_agency_name=agency_name)}

        new_trips_to_create: dict[str, Trip] = {}
        sig_counts: dict[str, int] = defaultdict(int)
        sig_sample: dict[str, str] = {}

        for g_id, info in trip_data.items():
            l_id  = route_to_line.get(info["route_id"])
            stops = trip_stops_ordered.get(g_id)
            if not l_id or not stops:
                continue
            ordered_stop_ids = [s[1] for s in stops]
            sig = _build_signature(l_id, info["dir"], ordered_stop_ids)
            sig_counts[sig] += 1
            if sig not in sig_sample:
                sig_sample[sig] = g_id
            if sig not in sig_to_trip_id and sig not in new_trips_to_create:
                new_trips_to_create[sig] = Trip(
                    line_id=l_id, line_agency_name=agency_name,
                    direction=info["dir"], signature=sig,
                    start_stop_id=ordered_stop_ids[0], terminus_stop_id=ordered_stop_ids[-1],
                    start_agency_name=agency_name, terminus_agency_name=agency_name,
                )

        t0 = time.time()
        if new_trips_to_create:
            session.add_all(new_trips_to_create.values())
            session.flush()
            ts_rows = []
            for sig, trip in new_trips_to_create.items():
                sig_to_trip_id[sig] = trip.id
                sample_g_id = sig_sample[sig]
                for idx, (_, stop_id) in enumerate(trip_stops_ordered[sample_g_id]):
                    ts_rows.append({"trip_id": trip.id, "stop_stop_id": stop_id,
                                    "stop_agency_name": agency_name, "sequence": idx})
            for batch in _chunked(ts_rows, BATCH_SIZE):
                session.bulk_insert_mappings(TripStop, batch)
        print(f"  canonical Trips/TripStops flushed ({len(new_trips_to_create)} new) in {time.time()-t0:.2f}s")

        session.bulk_update_mappings(Trip, [
            {"id": sig_to_trip_id[s], "trip_count": c}
            for s, c in sig_counts.items() if s in sig_to_trip_id
        ])

        t0 = time.time()
        best_q = session.query(
            Trip.line_id, Trip.direction, Trip.id,
            (sa.func.max(TripStop.sequence) * Trip.trip_count).label("score"),
        ).join(TripStop).filter(Trip.line_agency_name == agency_name).group_by(Trip.id).subquery()
        for line in session.query(Line).filter_by(agency_name=agency_name).all():
            for d in [0, 1]:
                best = session.query(best_q.c.id).filter(
                    best_q.c.line_id == line.id, best_q.c.direction == d,
                ).order_by(best_q.c.score.desc()).first()
                if best:
                    setattr(line, f"best_trip_{d}_id", best.id)
        print(f"  best trips updated in {time.time()-t0:.2f}s")

        # Snapshot BEFORE any deletions — raw_gtfs_stop_time still has old canonical_trip_stop_ids
        led_stop_snapshot = _snapshot_led_stop_mapping(session)
        print(f"  led_stop_snapshot: {len(led_stop_snapshot)} entries captured")

        # Delete raw rows BEFORE orphan trip_stops — raw_gtfs_stop_time has a FK on trip_stop
        t0 = time.time()
        session.execute(sa.text("""DELETE FROM raw_gtfs_stop_time
            WHERE raw_trip_id IN (SELECT id FROM raw_gtfs_trip WHERE agency_name = :a)"""),
            {"a": agency_name})
        session.execute(sa.text("DELETE FROM raw_gtfs_trip WHERE agency_name = :a"), {"a": agency_name})
        session.flush()
        print(f"  old raw rows deleted in {time.time()-t0:.2f}s")

        t0 = time.time()
        active_sigs = set(sig_counts.keys())
        orphan_trips = session.query(Trip).filter(
            Trip.line_agency_name == agency_name,
            Trip.signature.notin_(active_sigs),
        ).all()
        if orphan_trips:
            orphan_ids = [t.id for t in orphan_trips]
            # Nullify line.best_trip_*_id references before deleting trips
            session.execute(sa.text("""
                UPDATE line SET best_trip_0_id = NULL
                WHERE best_trip_0_id = ANY(:ids) AND agency_name = :a
            """), {"ids": orphan_ids, "a": agency_name})
            session.execute(sa.text("""
                UPDATE line SET best_trip_1_id = NULL
                WHERE best_trip_1_id = ANY(:ids) AND agency_name = :a
            """), {"ids": orphan_ids, "a": agency_name})
            session.query(TripStop).filter(
                TripStop.trip_id.in_(orphan_ids)
            ).delete(synchronize_session=False)
            session.query(Trip).filter(
                Trip.id.in_(orphan_ids)
            ).delete(synchronize_session=False)
            print(f"  {len(orphan_trips)} orphan canonical trips deleted in {time.time()-t0:.2f}s")
        else:
            print(f"  no orphan canonical trips to delete")

        t0 = time.time()
        raw_trip_rows = []
        for g_id, info in trip_data.items():
            l_id  = route_to_line.get(info["route_id"])
            stops = trip_stops_ordered.get(g_id)
            if not l_id or not stops:
                continue
            sig = _build_signature(l_id, info["dir"], [s[1] for s in stops])
            raw_trip_rows.append({
                "gtfs_trip_id":      g_id,
                "agency_name":       agency_name,
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

        del trip_stops_ordered

        t0 = time.time()
        gtfs_id_to_raw_pk:    dict[str, int] = {}
        gtfs_id_to_canonical: dict[str, int] = {}
        for r in (session.query(RawGtfsTrip.gtfs_trip_id, RawGtfsTrip.id, RawGtfsTrip.canonical_trip_id)
                         .filter_by(agency_name=agency_name)):
            gtfs_id_to_raw_pk[r.gtfs_trip_id] = r.id
            if r.canonical_trip_id is not None:
                gtfs_id_to_canonical[r.gtfs_trip_id] = r.canonical_trip_id
        print(f"  raw_trip_id map built ({len(gtfs_id_to_raw_pk)} entries) in {time.time()-t0:.2f}s")

        t0 = time.time()
        canonical_ids = set(gtfs_id_to_canonical.values())
        trip_stop_map: dict[tuple[int, str], int] = {
            (ts.trip_id, ts.stop_stop_id): ts.id
            for ts in (session.query(TripStop.id, TripStop.trip_id, TripStop.stop_stop_id)
                               .filter(TripStop.trip_id.in_(canonical_ids)))
        }
        print(f"  trip_stop map built ({len(trip_stop_map)} entries) in {time.time()-t0:.2f}s")

        t0 = time.time()
        mapped = inserted = 0
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
                batch.append({"raw_trip_id": raw_pk, "stop_sequence": int(row["stop_sequence"]),
                              "stop_id": stop_id,
                              "arrival_seconds":        _parse_seconds(row.get("arrival_time", "")),
                              "departure_seconds":      _parse_seconds(row.get("departure_time", "")),
                              "canonical_trip_stop_id": ts_id})
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
        print(f"{agency_name} Trips imported in {time.time()-tic:.2f}s")

        # ── Réparer les liens trip_stop_led_link cassés ───────────────────────
        _rebuild_trip_stop_led_links(session, agency_name, snapshot=led_stop_snapshot)
        session.commit()

        refresh_active_intervals()

    finally:
        session.close()


def import_gtfs_static(agency_name: str, zip_bytes: bytes, country: str = "Belgium") -> None:
    """Import all static GTFS data for agency_name from the raw ZIP bytes."""
    print(f"[{time.strftime('%H:%M:%S')}] GTFS static import — {agency_name}")
    gtfs = load_text_files(zip_bytes)
    if "routes.txt"  in gtfs: _import_lines(agency_name, gtfs["routes.txt"])
    if "stops.txt"   in gtfs: _import_stops(agency_name, gtfs["stops.txt"])
    if "calendar.txt" in gtfs or "calendar_dates.txt" in gtfs:
        _import_calendar(agency_name, gtfs.get("calendar.txt", ""), gtfs.get("calendar_dates.txt", ""))
    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        if "trips.txt" in gtfs and "stop_times.txt" in zf.namelist():
            _import_trips(agency_name, gtfs["trips.txt"], zip_bytes)


# ---------------------------------------------------------------------------
# GtfsOperator — base class for transit operators
# ---------------------------------------------------------------------------

class GtfsOperator:
    AGENCY_NAME:     str = ""
    COUNTRY:         str = "Belgium"
    GTFS_STATIC_URL: str = ""
    GTFS_RT_URL:     str = ""
    STATIC_TIMEOUT:  int = 120
    RT_TIMEOUT:      int = 10

    def __init__(self):
        pass

    @property
    def _headers(self) -> dict:
        return {}

    def _fetch_zip_bytes(self) -> bytes:
        print(f"[{time.strftime('%H:%M:%S')}] [{self.AGENCY_NAME}] Téléchargement GTFS statique…")
        r = requests.get(self.GTFS_STATIC_URL, headers=self._headers, timeout=self.STATIC_TIMEOUT)
        if r.status_code != 200:
            raise RuntimeError(f"[{self.AGENCY_NAME}] GTFS static HTTP {r.status_code}: {r.text[:200]}")
        print(f"  [{self.AGENCY_NAME}] Téléchargé ({len(r.content)/1024/1024:.1f} MB)")
        return r.content

    def import_static(self) -> None:
        import_gtfs_static(self.AGENCY_NAME, self._fetch_zip_bytes(), self.COUNTRY)

    def _fetch_rt_raw(self) -> bytes:
        r = requests.get(self.GTFS_RT_URL, headers=self._headers, timeout=self.RT_TIMEOUT)
        if r.status_code != 200:
            raise RuntimeError(f"[{self.AGENCY_NAME}] RT HTTP {r.status_code}: {r.text[:200]}")
        return r.content

    def update_realtime(self) -> None:
        if not self.GTFS_RT_URL:
            return

        from datetime import datetime as _dt

        tic = time.time()
        print(f"[{time.strftime('%H:%M:%S')}] [{self.AGENCY_NAME}] Mise à jour Temps Réel…")

        try:
            raw = self._fetch_rt_raw()
        except Exception as e:
            print(f"  [{self.AGENCY_NAME}] ERREUR fetch RT: {e}")
            return

        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(raw)
        entities = [e for e in feed.entity if e.HasField("trip_update")]
        print(f"  [{self.AGENCY_NAME}] {len(entities)} TripUpdates reçus")
        if not entities:
            return

        feed_ts = feed.header.timestamp or int(time.time())
        today   = _dt.now().strftime("%Y%m%d")
        now_dt  = _dt.utcnow()

        rows = []
        skipped = 0
        for entity in entities:
            tu = entity.trip_update
            gtfs_trip_id = tu.trip.trip_id
            if not gtfs_trip_id:
                skipped += 1
                continue
            start_date = tu.trip.start_date or today
            for stu in tu.stop_time_update:
                arr_ts    = stu.arrival.time    if stu.HasField("arrival")   else None
                dep_ts    = stu.departure.time  if stu.HasField("departure") else None
                arr_delay = stu.arrival.delay   if stu.HasField("arrival")   else None
                dep_delay = stu.departure.delay if stu.HasField("departure") else None
                rows.append({
                    "gtfs_trip_id":           gtfs_trip_id,
                    "agency_name":            self.AGENCY_NAME,
                    "start_date":             start_date,
                    "stop_sequence":          stu.stop_sequence,
                    "stop_id":                stu.stop_id or None,
                    "predicted_arrival_ts":   int(arr_ts)    if arr_ts    is not None else None,
                    "predicted_departure_ts": int(dep_ts)    if dep_ts    is not None else None,
                    "delay_seconds":          int(arr_delay if arr_delay is not None else dep_delay)
                                              if (arr_delay is not None or dep_delay is not None) else None,
                    "schedule_relationship":  int(stu.schedule_relationship),
                    "feed_timestamp":         int(feed_ts),
                    "updated_at":             now_dt,
                })

        if skipped:
            print(f"  [{self.AGENCY_NAME}] Ignorés (pas de trip_id): {skipped}")
        if not rows:
            return

        upsert_sql = sa.text("""
            INSERT INTO realtime_stop_time_override
                (gtfs_trip_id, agency_name, start_date, stop_sequence, stop_id,
                 predicted_arrival_ts, predicted_departure_ts, delay_seconds,
                 schedule_relationship, feed_timestamp, updated_at)
            VALUES
                (:gtfs_trip_id, :agency_name, :start_date, :stop_sequence, :stop_id,
                 :predicted_arrival_ts, :predicted_departure_ts, :delay_seconds,
                 :schedule_relationship, :feed_timestamp, :updated_at)
            ON CONFLICT ON CONSTRAINT uq_rt_override_trip_date_seq
            DO UPDATE SET
                stop_id                = EXCLUDED.stop_id,
                predicted_arrival_ts   = EXCLUDED.predicted_arrival_ts,
                predicted_departure_ts = EXCLUDED.predicted_departure_ts,
                delay_seconds          = EXCLUDED.delay_seconds,
                schedule_relationship  = EXCLUDED.schedule_relationship,
                feed_timestamp         = EXCLUDED.feed_timestamp,
                updated_at             = EXCLUDED.updated_at
        """)

        session = next(get_db())
        try:
            for batch in _chunked(rows, BATCH_SIZE):
                session.execute(upsert_sql, batch)
            session.execute(sa.text(
                "DELETE FROM realtime_stop_time_override "
                "WHERE agency_name = :a AND start_date < :today"
            ), {"a": self.AGENCY_NAME, "today": today})
            session.commit()
            print(f"  [{self.AGENCY_NAME}] {len(rows)} overrides upsertés en {time.time()-tic:.2f}s")

            # For agencies that send delay-based RT (no absolute timestamps),
            # compute predicted_arrival/departure_ts from schedule + delay so the matview
            # can use them for is_realtime detection and adjusted arrival times.
            updated = session.execute(sa.text("""
                UPDATE realtime_stop_time_override rto
                SET
                    predicted_arrival_ts = (
                        EXTRACT(epoch FROM (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Brussels')::date)::bigint
                        + rst.arrival_seconds + rto.delay_seconds
                    ),
                    predicted_departure_ts = (
                        EXTRACT(epoch FROM (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Brussels')::date)::bigint
                        + rst.departure_seconds + rto.delay_seconds
                    )
                FROM raw_gtfs_stop_time rst
                JOIN raw_gtfs_trip rgt ON rgt.id = rst.raw_trip_id
                WHERE rgt.gtfs_trip_id = rto.gtfs_trip_id
                  AND rgt.agency_name   = rto.agency_name
                  AND rst.stop_sequence = rto.stop_sequence
                  AND rto.agency_name   = :agency
                  AND rto.start_date    = :today
                  AND NULLIF(rto.predicted_arrival_ts, 0) IS NULL
                  AND rto.delay_seconds IS NOT NULL
                  AND (rto.schedule_relationship IS NULL OR rto.schedule_relationship != 1)
            """), {"agency": self.AGENCY_NAME, "today": today}).rowcount
            if updated:
                session.commit()
                print(f"  [{self.AGENCY_NAME}] {updated} timestamps calculés depuis delay_seconds")

            refresh_active_intervals()
        except Exception as e:
            session.rollback()
            print(f"  [{self.AGENCY_NAME}] ERREUR upsert RT: {e}")
            import traceback
            traceback.print_exc()
        finally:
            session.close()