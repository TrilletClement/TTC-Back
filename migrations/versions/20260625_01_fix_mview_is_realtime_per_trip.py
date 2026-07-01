"""Fix active_incoming_intervals: is_realtime now checked per trip, not per stop.

Previously, is_realtime = True only when predicted_arrival_ts > 0 exists for
THIS specific stop_sequence.  A trip actively tracked in RT but missing a
prediction for one stop would show that stop as theoretical (orange) even
though the trip is realtime-tracked.

Fix: the EXISTS now checks whether ANY stop in the same trip (same
gtfs_trip_id + agency_name + start_date) has a valid RT prediction.  If the
trip is in the RT feed, all its intervals are treated as realtime.

Revision ID: 20260625_01
Revises: 20260624_04
Create Date: 2026-06-25
"""
from typing import Sequence, Union
from alembic import op

revision: str = "20260625_01"
down_revision: Union[str, None] = "20260624_04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DROP = "DROP MATERIALIZED VIEW IF EXISTS active_incoming_intervals"

_BRUSSELS_MIDNIGHT = (
    "EXTRACT(EPOCH FROM "
    "  date_trunc('day', CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Brussels') "
    "  AT TIME ZONE 'Europe/Brussels'"
    ")::bigint"
)

_CREATE = f"""
CREATE MATERIALIZED VIEW active_incoming_intervals AS
WITH today_trips AS (
    SELECT rgt.id AS raw_trip_id
    FROM raw_gtfs_trip rgt
    JOIN raw_gtfs_service_date svc
      ON svc.service_id  = rgt.service_id
     AND svc.agency_name = rgt.agency_name
     AND svc.date        = TO_CHAR(CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Brussels', 'YYYYMMDD')
),
all_trip_stops AS (
    SELECT
        rst.raw_trip_id,
        rgt.gtfs_trip_id,
        rgt.agency_name,
        rst.stop_sequence,
        rst.canonical_trip_stop_id,
        rst.arrival_seconds,
        rst.departure_seconds,
        LAG(rst.departure_seconds) OVER (
            PARTITION BY rst.raw_trip_id ORDER BY rst.stop_sequence
        ) AS prev_dep_sec,
        LAG(rst.stop_sequence) OVER (
            PARTITION BY rst.raw_trip_id ORDER BY rst.stop_sequence
        ) AS prev_seq
    FROM raw_gtfs_stop_time rst
    JOIN today_trips tt ON tt.raw_trip_id = rst.raw_trip_id
    JOIN raw_gtfs_trip rgt ON rgt.id = rst.raw_trip_id
),
canonical_stops AS (
    SELECT * FROM all_trip_stops
    WHERE canonical_trip_stop_id IS NOT NULL
      AND prev_dep_sec IS NOT NULL
      AND canonical_trip_stop_id IN (
          SELECT DISTINCT trip_stop_id FROM trip_stop_led_link
      )
),
with_effective AS (
    SELECT
        cs.raw_trip_id,
        cs.stop_sequence,
        cs.canonical_trip_stop_id,
        cs.gtfs_trip_id,
        cs.agency_name,
        -- led_on_from: RT dep of previous stop (if > 0)
        --              ELSE RT arrival at this stop minus static travel time
        --              ELSE static midnight + static prev dep
        COALESCE(
            (SELECT ov.predicted_departure_ts
             FROM realtime_stop_time_override ov
             WHERE ov.gtfs_trip_id  = cs.gtfs_trip_id
               AND ov.agency_name   = cs.agency_name
               AND ov.stop_sequence = cs.prev_seq
               AND ov.start_date    = TO_CHAR(CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Brussels', 'YYYYMMDD')
               AND ov.predicted_departure_ts > 0
               AND (ov.schedule_relationship IS NULL OR ov.schedule_relationship != 1)
             LIMIT 1),
            (SELECT ov.predicted_arrival_ts - (cs.arrival_seconds - cs.prev_dep_sec)
             FROM realtime_stop_time_override ov
             WHERE ov.gtfs_trip_id  = cs.gtfs_trip_id
               AND ov.agency_name   = cs.agency_name
               AND ov.stop_sequence = cs.stop_sequence
               AND ov.start_date    = TO_CHAR(CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Brussels', 'YYYYMMDD')
               AND ov.predicted_arrival_ts > 0
               AND (ov.schedule_relationship IS NULL OR ov.schedule_relationship != 1)
             LIMIT 1),
            {_BRUSSELS_MIDNIGHT} + cs.prev_dep_sec
        ) AS led_on_from,
        -- led_on_until: RT arrival at this stop (if > 0), else static
        COALESCE(
            (SELECT ov.predicted_arrival_ts
             FROM realtime_stop_time_override ov
             WHERE ov.gtfs_trip_id  = cs.gtfs_trip_id
               AND ov.agency_name   = cs.agency_name
               AND ov.stop_sequence = cs.stop_sequence
               AND ov.start_date    = TO_CHAR(CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Brussels', 'YYYYMMDD')
               AND ov.predicted_arrival_ts > 0
               AND (ov.schedule_relationship IS NULL OR ov.schedule_relationship != 1)
             LIMIT 1),
            {_BRUSSELS_MIDNIGHT} + cs.arrival_seconds
        ) AS led_on_until,
        -- is_realtime: true if ANY stop of this trip has a valid RT prediction.
        -- Checked per trip (not per stop) so that stops without an individual
        -- predicted_arrival_ts still show as realtime when the trip is tracked.
        EXISTS (
            SELECT 1 FROM realtime_stop_time_override ov
            WHERE ov.gtfs_trip_id  = cs.gtfs_trip_id
              AND ov.agency_name   = cs.agency_name
              AND ov.start_date    = TO_CHAR(CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Brussels', 'YYYYMMDD')
              AND ov.predicted_arrival_ts > 0
              AND (ov.schedule_relationship IS NULL OR ov.schedule_relationship != 1)
        ) AS is_realtime,
        NOT EXISTS (
            SELECT 1 FROM realtime_stop_time_override skip_ov
            WHERE skip_ov.gtfs_trip_id  = cs.gtfs_trip_id
              AND skip_ov.agency_name   = cs.agency_name
              AND skip_ov.stop_sequence = cs.stop_sequence
              AND skip_ov.start_date    = TO_CHAR(CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Brussels', 'YYYYMMDD')
              AND skip_ov.schedule_relationship = 1
        ) AS not_skipped
    FROM canonical_stops cs
)
SELECT
    raw_trip_id,
    stop_sequence,
    canonical_trip_stop_id,
    led_on_from,
    led_on_until,
    is_realtime
FROM with_effective
WHERE not_skipped
WITH NO DATA
"""


def upgrade() -> None:
    op.execute(_DROP)
    op.execute(_CREATE)
    op.execute(
        "CREATE UNIQUE INDEX uq_active_incoming_intervals_trip_seq "
        "ON active_incoming_intervals (raw_trip_id, stop_sequence)"
    )
    op.execute(
        "CREATE INDEX ix_active_incoming_intervals_ts_id "
        "ON active_incoming_intervals (canonical_trip_stop_id)"
    )
    op.execute(
        "CREATE INDEX ix_active_incoming_intervals_range "
        "ON active_incoming_intervals (led_on_from, led_on_until)"
    )
    op.execute("REFRESH MATERIALIZED VIEW active_incoming_intervals")


def downgrade() -> None:
    op.execute(_DROP)
