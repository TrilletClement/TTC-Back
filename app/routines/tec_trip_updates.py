#!/usr/bin/env python3
"""
TEC GTFS-RT TripUpdates poller.

Fetches the TEC TripUpdates protobuf feed and upserts predicted arrival /
departure timestamps into realtime_stop_time_override.

CONTRACT: This module does NOT compute LED state.  It only writes override
rows.  The active_incoming_intervals view (or the equivalent Python query in
boardService) reads those rows at board-state request time.

Scheduled every 30 seconds via scheduler.py.
"""

if __name__ == "__main__":
    import sys, os
    BASE_DIR   = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
    FASTAPI_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
    sys.path.insert(0, BASE_DIR)
    sys.path.insert(0, FASTAPI_DIR)

import os
import time
from collections import defaultdict
from datetime import datetime

import requests
import sqlalchemy as sa
from google.transit import gtfs_realtime_pb2

from app.orm_models.db import get_db

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

AGENCY_NAME = "TEC"

# Belgian Mobility Commons API key (same key used for static GTFS).
BMC_API_KEY = (
    os.environ.get("BMC_API_KEY", "")
    or os.environ.get("TEC_API_KEY", "")
).strip()
BMC_HEADERS = {"bmc-partner-key": BMC_API_KEY} if BMC_API_KEY else {}
print(f"[tec_trip_updates] BMC_API_KEY={'***' + BMC_API_KEY[-4:] if len(BMC_API_KEY) > 4 else '(empty — anonymous)'}")

TRIP_UPDATES_URL = (
    os.environ.get("TEC_TRIP_UPDATES_URL")
    or "https://opendata-discovery-gtfs-realtime.api.production.belgianmobility.io"
       "/api/gtfs-rt/tec/TripUpdates.pbf"
)

BATCH_SIZE = 2000

# Cleanup: delete override rows older than this many days
OVERRIDE_RETENTION_DAYS = 1


# ---------------------------------------------------------------------------
# Helpers
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


def _fetch_trip_updates_feed():
    response = requests.get(TRIP_UPDATES_URL, headers=BMC_HEADERS, timeout=15)
    if response.status_code != 200:
        raise RuntimeError(
            f"TEC TripUpdates HTTP {response.status_code}: {response.text[:200]}"
        )
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(response.content)
    return feed


# ---------------------------------------------------------------------------
# Main poller
# ---------------------------------------------------------------------------

def fetch_tec_trip_updates():
    """
    Fetch TEC GTFS-RT TripUpdates and upsert into realtime_stop_time_override.

    For each TripUpdate → StopTimeUpdate we store:
      - predicted_arrival_ts   (Unix timestamp, seconds)
      - predicted_departure_ts (Unix timestamp, seconds)
      - delay_seconds          (from arrival.delay or departure.delay)
      - schedule_relationship  (0=SCHEDULED, 1=SKIPPED, 2=NO_DATA)

    Rows are upserted on the unique key
    (gtfs_trip_id, agency_name, start_date, stop_sequence).

    Override rows older than today are cleaned up at the end of each run.
    """
    tic = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] TEC TripUpdates fetch démarré…")

    try:
        feed = _fetch_trip_updates_feed()
    except Exception as e:
        print(f"  ERREUR fetch TripUpdates: {e}")
        return

    entities = [e for e in feed.entity if e.HasField("trip_update")]
    print(f"  Feed reçu: {len(entities)} TripUpdates")

    if not entities:
        print("  Aucun TripUpdate reçu, ignoré.")
        return

    feed_ts  = feed.header.timestamp or int(time.time())
    today    = datetime.now().strftime("%Y%m%d")
    now_dt   = datetime.utcnow()

    # ── Build upsert rows ─────────────────────────────────────────────────────
    rows = []
    skipped_no_trip = 0

    for entity in entities:
        tu = entity.trip_update
        gtfs_trip_id = tu.trip.trip_id
        if not gtfs_trip_id:
            skipped_no_trip += 1
            continue

        # start_date from the feed, fall back to today
        start_date = tu.trip.start_date or today

        for stu in tu.stop_time_update:
            arr_ts  = stu.arrival.time   if stu.HasField("arrival")   else None
            dep_ts  = stu.departure.time if stu.HasField("departure")  else None
            arr_delay = stu.arrival.delay   if stu.HasField("arrival")  else None
            dep_delay = stu.departure.delay if stu.HasField("departure") else None
            delay = arr_delay if arr_delay is not None else dep_delay

            rows.append({
                "gtfs_trip_id":          gtfs_trip_id,
                "agency_name":           AGENCY_NAME,
                "start_date":            start_date,
                "stop_sequence":         stu.stop_sequence,
                "stop_id":               stu.stop_id or None,
                "predicted_arrival_ts":  int(arr_ts) if arr_ts else None,
                "predicted_departure_ts": int(dep_ts) if dep_ts else None,
                "delay_seconds":         int(delay) if delay is not None else None,
                "schedule_relationship": int(stu.schedule_relationship),
                "feed_timestamp":        int(feed_ts),
                "updated_at":            now_dt,
            })

    if skipped_no_trip:
        print(f"  Ignorés (pas de trip_id): {skipped_no_trip}")

    if not rows:
        print("  Aucune ligne à upserter.")
        return

    # ── Upsert ────────────────────────────────────────────────────────────────
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
        total_upserted = 0
        for batch in _chunked(rows, BATCH_SIZE):
            session.execute(upsert_sql, batch)
            total_upserted += len(batch)

        # ── Cleanup old overrides (keep today only) ───────────────────────────
        session.execute(sa.text("""
            DELETE FROM realtime_stop_time_override
            WHERE agency_name = :agency
              AND start_date  < :today
        """), {"agency": AGENCY_NAME, "today": today})

        session.commit()
        print(f"  Upserted {total_upserted} overrides in {time.time()-tic:.2f}s")

        from app.routines.refresh_intervals import refresh_active_intervals
        refresh_active_intervals()

    except Exception as e:
        session.rollback()
        print(f"  ERREUR upsert overrides: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Lancement TEC TripUpdates poller…")
    fetch_tec_trip_updates()
