"""Fix realtime zero timestamps in active_incoming_intervals view.

TEC (and potentially other operators) send predicted_departure_ts = 0
in their GTFS-RT feed instead of omitting the field. COALESCE treats 0
as a valid value (non-NULL), so those rows override the static schedule
with led_on_from = 0 (Unix epoch 1970) — making those LEDs appear
permanently active.

Fix: wrap the realtime subquery in NULLIF(..., 0) so that a zero
timestamp falls back to the static schedule, same as if it were absent.

Revision ID: 20260614_01
Revises: 20260613_02
Create Date: 2026-06-14
"""
from typing import Sequence, Union
from alembic import op

revision: str = "20260614_01"
down_revision: Union[str, None] = "20260613_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DROP = "DROP MATERIALIZED VIEW IF EXISTS active_incoming_intervals"
_CREATE = """
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
        COALESCE(
            NULLIF((SELECT ov.predicted_departure_ts
             FROM realtime_stop_time_override ov
             WHERE ov.gtfs_trip_id  = cs.gtfs_trip_id
               AND ov.agency_name   = cs.agency_name
               AND ov.stop_sequence = cs.prev_seq
               AND ov.start_date    = TO_CHAR(CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Brussels', 'YYYYMMDD')
               AND (ov.schedule_relationship IS NULL OR ov.schedule_relationship != 1)
             LIMIT 1), 0),
            EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Brussels')::date)::bigint
            + cs.prev_dep_sec
        ) AS led_on_from,
        COALESCE(
            NULLIF((SELECT ov.predicted_arrival_ts
             FROM realtime_stop_time_override ov
             WHERE ov.gtfs_trip_id  = cs.gtfs_trip_id
               AND ov.agency_name   = cs.agency_name
               AND ov.stop_sequence = cs.stop_sequence
               AND ov.start_date    = TO_CHAR(CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Brussels', 'YYYYMMDD')
               AND (ov.schedule_relationship IS NULL OR ov.schedule_relationship != 1)
             LIMIT 1), 0),
            EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Brussels')::date)::bigint
            + cs.arrival_seconds
        ) AS led_on_until,
        EXISTS (
            SELECT 1 FROM realtime_stop_time_override ov
            WHERE ov.gtfs_trip_id  = cs.gtfs_trip_id
              AND ov.agency_name   = cs.agency_name
              AND ov.stop_sequence = cs.stop_sequence
              AND ov.start_date    = TO_CHAR(CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Brussels', 'YYYYMMDD')
              AND (ov.schedule_relationship IS NULL OR ov.schedule_relationship != 1)
              AND NULLIF(ov.predicted_arrival_ts, 0) IS NOT NULL
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
