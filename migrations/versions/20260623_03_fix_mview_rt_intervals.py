"""Fix active_incoming_intervals: correct led_on_from when RT arrival exists but not previous dep.

Two bugs fixed:

1. When the RT feed provides predicted_arrival_ts for a stop but NOT
   predicted_departure_ts for the previous stop, led_on_from fell back to
   the static midnight + prev_dep_sec (the scheduled departure). If the bus
   runs significantly late (e.g. TEC buses with 2h RT delay), this created
   multi-hour intervals. Fix: compute led_on_from as RT_arrival - static_travel_time
   (the scheduled travel time between the two stops anchored on the RT arrival).

2. Some RT feeds (notably TEC) emit predicted_arrival_ts = 0 instead of NULL
   when they have no real prediction. This caused COALESCE to pick 0 (Unix
   epoch 1970-01-01) instead of the static fallback. Fix: filter timestamps > 0.

Revision ID: 20260623_03
Revises: 20260623_02
Create Date: 2026-06-23
"""
from typing import Sequence, Union
from alembic import op

revision: str = "20260623_03"
down_revision: Union[str, None] = "20260623_02"
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
        -- is_realtime: true if arrival prediction comes from RT (and is valid)
        EXISTS (
            SELECT 1 FROM realtime_stop_time_override ov
            WHERE ov.gtfs_trip_id  = cs.gtfs_trip_id
              AND ov.agency_name   = cs.agency_name
              AND ov.stop_sequence = cs.stop_sequence
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
