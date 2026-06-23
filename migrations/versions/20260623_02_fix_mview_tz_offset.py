"""Fix active_incoming_intervals matview timezone offset.

The static schedule formula used EXTRACT(EPOCH FROM date::date) which returns UTC
midnight, but GTFS arrival_seconds are seconds since Brussels local midnight. This
created a 7200-second (2h CEST) offset, causing static-schedule intervals to be
2 hours wrong. Fix: use Brussels midnight epoch instead of UTC midnight.

Revision ID: 20260623_02
Revises: 20260623_01
Create Date: 2026-06-23
"""
from typing import Sequence, Union
from alembic import op

revision: str = "20260623_02"
down_revision: Union[str, None] = "20260623_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DROP = "DROP MATERIALIZED VIEW IF EXISTS active_incoming_intervals"

# Brussels midnight epoch:
#   date_trunc('day', CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Brussels') → timestamp (no tz, Brussels)
#   ... AT TIME ZONE 'Europe/Brussels' → timestamptz (UTC equivalent of Brussels midnight)
#   EXTRACT(EPOCH FROM ...) → Unix epoch of Brussels midnight
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
      -- Only compute intervals for stops actually assigned to a LED
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
        COALESCE(
            (SELECT ov.predicted_departure_ts
             FROM realtime_stop_time_override ov
             WHERE ov.gtfs_trip_id  = cs.gtfs_trip_id
               AND ov.agency_name   = cs.agency_name
               AND ov.stop_sequence = cs.prev_seq
               AND ov.start_date    = TO_CHAR(CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Brussels', 'YYYYMMDD')
               AND (ov.schedule_relationship IS NULL OR ov.schedule_relationship != 1)
             LIMIT 1),
            {_BRUSSELS_MIDNIGHT} + cs.prev_dep_sec
        ) AS led_on_from,
        COALESCE(
            (SELECT ov.predicted_arrival_ts
             FROM realtime_stop_time_override ov
             WHERE ov.gtfs_trip_id  = cs.gtfs_trip_id
               AND ov.agency_name   = cs.agency_name
               AND ov.stop_sequence = cs.stop_sequence
               AND ov.start_date    = TO_CHAR(CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Brussels', 'YYYYMMDD')
               AND (ov.schedule_relationship IS NULL OR ov.schedule_relationship != 1)
             LIMIT 1),
            {_BRUSSELS_MIDNIGHT} + cs.arrival_seconds
        ) AS led_on_until,
        EXISTS (
            SELECT 1 FROM realtime_stop_time_override ov
            WHERE ov.gtfs_trip_id  = cs.gtfs_trip_id
              AND ov.agency_name   = cs.agency_name
              AND ov.stop_sequence = cs.stop_sequence
              AND ov.start_date    = TO_CHAR(CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Brussels', 'YYYYMMDD')
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
