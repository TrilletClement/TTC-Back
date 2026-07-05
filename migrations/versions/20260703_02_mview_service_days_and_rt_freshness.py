"""active_incoming_intervals v3 — service-day aware + RT freshness.

Two correctness fixes so that any remaining "theoretical" display is
attributable to the upstream feeds, never to this code:

1. Service days: GTFS trips can run past midnight (times > 24:00:00 belong to
   the *previous* service day).  The view now covers today's service day AND
   yesterday's cross-midnight trips (17k+ trips network-wide), each with its
   own midnight epoch, and joins RT overrides on the trip's own start_date
   instead of a global "today".  Night buses (Noctis, TEC/De Lijn night lines)
   were previously dropped entirely between midnight and end of service.

2. Freshness: is_realtime previously stayed true all day once a trip had
   appeared in the feed, even after tracking was lost.  It is now true only if
   the trip is still present in the agency's most recent feed (within 120 s of
   the agency's max feed_timestamp — relative, so a polling outage on OUR side
   does not flip everything to theoretical).

3. Delay propagation (GTFS-RT rule): feeds like TEC only send predictions for
   a horizon around the vehicle and mark later stops NO_DATA.  For stops
   without their own prediction, the last specified delay (stop_sequence <=
   this stop, schedule_relationship 0) now shifts the static window — a bus
   21 min late no longer traverses downstream stops with windows 21 min in
   the past (LED stayed dark).

Revision ID: 20260703_02
Revises: 20260703_01
Create Date: 2026-07-03
"""
from typing import Sequence, Union
from alembic import op

revision: str = "20260703_02"
down_revision: Union[str, None] = "20260703_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DROP = "DROP MATERIALIZED VIEW IF EXISTS active_incoming_intervals"

_CREATE = """
CREATE MATERIALIZED VIEW active_incoming_intervals AS
WITH service_days AS (
    -- Today and yesterday (Brussels): trips with times > 24:00:00 belong to
    -- yesterday's service day and are still running after midnight.
    SELECT
        TO_CHAR(CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Brussels', 'YYYYMMDD') AS service_date,
        EXTRACT(EPOCH FROM
            date_trunc('day', CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Brussels')
            AT TIME ZONE 'Europe/Brussels'
        )::bigint AS midnight_epoch,
        FALSE AS is_yesterday
    UNION ALL
    SELECT
        TO_CHAR((CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Brussels')::date - 1, 'YYYYMMDD'),
        EXTRACT(EPOCH FROM
            (date_trunc('day', CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Brussels') - interval '1 day')
            AT TIME ZONE 'Europe/Brussels'
        )::bigint,
        TRUE
),
feed_freshness AS MATERIALIZED (
    -- Latest feed timestamp per agency.  Freshness is relative to this (not
    -- to the wall clock) so a polling gap on our side keeps the last known
    -- state instead of flipping every trip to theoretical.
    -- MATERIALIZED: computed once — inlined it would be re-aggregated per row.
    SELECT agency_name, MAX(feed_timestamp) AS latest_ts
    FROM realtime_stop_time_override
    GROUP BY agency_name
),
led_trips AS MATERIALIZED (
    -- Only trips whose canonical pattern contains a LED-linked stop can
    -- produce rows.  Filtering trips here (not stops — LAG still needs every
    -- stop of a kept trip) shrinks the windowed set from ~1M stop_times to a
    -- few thousand.  Derived via canonical_trip_id (indexed) instead of
    -- scanning raw_gtfs_stop_time.
    SELECT rgt.id AS raw_trip_id
    FROM raw_gtfs_trip rgt
    WHERE rgt.canonical_trip_id IN (
        SELECT DISTINCT ts.trip_id
        FROM trip_stop_led_link tsl
        JOIN trip_stop ts ON ts.id = tsl.trip_stop_id
    )
),
cross_midnight AS MATERIALIZED (
    -- LED-relevant trips with stop times past 24:00:00 — the only ones still
    -- running on yesterday's service day.
    SELECT lt.raw_trip_id
    FROM led_trips lt
    WHERE EXISTS (
        SELECT 1 FROM raw_gtfs_stop_time rst
        WHERE rst.raw_trip_id = lt.raw_trip_id AND rst.arrival_seconds > 86400
    )
),
rt_trips AS MATERIALIZED (
    -- Trips with a valid RT prediction that are still present in their
    -- agency's most recent feed (within 120 s of the agency max) — computed
    -- once instead of an EXISTS probe per interval row.
    SELECT DISTINCT ov.gtfs_trip_id, ov.agency_name, ov.start_date
    FROM realtime_stop_time_override ov
    JOIN feed_freshness ff ON ff.agency_name = ov.agency_name
    WHERE ov.predicted_arrival_ts > 0
      AND (ov.schedule_relationship IS NULL OR ov.schedule_relationship != 1)
      AND ov.feed_timestamp >= ff.latest_ts - 120
),
active_trips AS (
    SELECT rgt.id AS raw_trip_id, sd.service_date, sd.midnight_epoch
    FROM raw_gtfs_trip rgt
    JOIN led_trips lt ON lt.raw_trip_id = rgt.id
    JOIN service_days sd ON TRUE
    JOIN raw_gtfs_service_date svc
      ON svc.service_id  = rgt.service_id
     AND svc.agency_name = rgt.agency_name
     AND svc.date        = sd.service_date
    WHERE NOT sd.is_yesterday
       OR rgt.id IN (SELECT raw_trip_id FROM cross_midnight)
),
all_trip_stops AS (
    SELECT
        rst.raw_trip_id,
        tt.service_date,
        tt.midnight_epoch,
        rgt.gtfs_trip_id,
        rgt.agency_name,
        rst.stop_sequence,
        rst.canonical_trip_stop_id,
        rst.arrival_seconds,
        rst.departure_seconds,
        LAG(rst.departure_seconds) OVER w AS prev_dep_sec,
        LAG(rst.stop_sequence)     OVER w AS prev_seq
    FROM raw_gtfs_stop_time rst
    JOIN active_trips tt ON tt.raw_trip_id = rst.raw_trip_id
    JOIN raw_gtfs_trip rgt ON rgt.id = rst.raw_trip_id
    WINDOW w AS (PARTITION BY rst.raw_trip_id, tt.service_date ORDER BY rst.stop_sequence)
),
canonical_stops AS (
    SELECT * FROM all_trip_stops
    WHERE canonical_trip_stop_id IS NOT NULL
      AND prev_dep_sec IS NOT NULL
      AND canonical_trip_stop_id IN (
          SELECT DISTINCT trip_stop_id FROM trip_stop_led_link
      )
)
SELECT
    cs.raw_trip_id,
    cs.service_date,
    cs.stop_sequence,
    cs.canonical_trip_stop_id,
    -- led_on_from: RT dep of previous stop (if > 0)
    --              ELSE RT arrival at this stop minus static travel time
    --              ELSE static prev dep + propagated delay (GTFS-RT rule:
    --                   the last specified delay applies to later stops)
    COALESCE(
        CASE WHEN prev_ov.predicted_departure_ts > 0
              AND (prev_ov.schedule_relationship IS NULL OR prev_ov.schedule_relationship != 1)
             THEN prev_ov.predicted_departure_ts END,
        CASE WHEN cur_ov.predicted_arrival_ts > 0
              AND (cur_ov.schedule_relationship IS NULL OR cur_ov.schedule_relationship != 1)
             THEN cur_ov.predicted_arrival_ts - (cs.arrival_seconds - cs.prev_dep_sec) END,
        cs.midnight_epoch + cs.prev_dep_sec + COALESCE(eff.delay_seconds, 0)
    ) AS led_on_from,
    -- led_on_until: RT arrival at this stop (if > 0), else static + propagated delay
    COALESCE(
        CASE WHEN cur_ov.predicted_arrival_ts > 0
              AND (cur_ov.schedule_relationship IS NULL OR cur_ov.schedule_relationship != 1)
             THEN cur_ov.predicted_arrival_ts END,
        cs.midnight_epoch + cs.arrival_seconds + COALESCE(eff.delay_seconds, 0)
    ) AS led_on_until,
    (rt.gtfs_trip_id IS NOT NULL) AS is_realtime
FROM canonical_stops cs
-- ≤ 1 row each, guaranteed by uq_rt_override_trip_date_seq
LEFT JOIN realtime_stop_time_override prev_ov
       ON prev_ov.gtfs_trip_id  = cs.gtfs_trip_id
      AND prev_ov.agency_name   = cs.agency_name
      AND prev_ov.start_date    = cs.service_date
      AND prev_ov.stop_sequence = cs.prev_seq
LEFT JOIN realtime_stop_time_override cur_ov
       ON cur_ov.gtfs_trip_id  = cs.gtfs_trip_id
      AND cur_ov.agency_name   = cs.agency_name
      AND cur_ov.start_date    = cs.service_date
      AND cur_ov.stop_sequence = cs.stop_sequence
LEFT JOIN rt_trips rt
       ON rt.gtfs_trip_id = cs.gtfs_trip_id
      AND rt.agency_name  = cs.agency_name
      AND rt.start_date   = cs.service_date
-- Propagated delay: feeds like TEC only predict a horizon around the vehicle
-- and mark later stops NO_DATA — without propagation, a delayed bus would
-- traverse those stops with static windows already in the past (LED dark).
LEFT JOIN LATERAL (
    SELECT d.delay_seconds
    FROM realtime_stop_time_override d
    WHERE d.gtfs_trip_id  = cs.gtfs_trip_id
      AND d.agency_name   = cs.agency_name
      AND d.start_date    = cs.service_date
      AND d.stop_sequence <= cs.stop_sequence
      AND d.delay_seconds IS NOT NULL
      AND d.delay_seconds >= -300
      AND (d.schedule_relationship IS NULL OR d.schedule_relationship = 0)
    ORDER BY d.stop_sequence DESC
    LIMIT 1
) eff ON TRUE
-- schedule_relationship 1 = SKIPPED: the stop will not be served
WHERE cur_ov.schedule_relationship IS DISTINCT FROM 1
WITH NO DATA
"""

# Previous definition (20260625_01) for downgrade
_BRUSSELS_MIDNIGHT_V2 = (
    "EXTRACT(EPOCH FROM "
    "  date_trunc('day', CURRENT_TIMESTAMP AT TIME ZONE 'Europe/Brussels') "
    "  AT TIME ZONE 'Europe/Brussels'"
    ")::bigint"
)

_CREATE_V2 = f"""
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
            {_BRUSSELS_MIDNIGHT_V2} + cs.prev_dep_sec
        ) AS led_on_from,
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
            {_BRUSSELS_MIDNIGHT_V2} + cs.arrival_seconds
        ) AS led_on_until,
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
        "CREATE UNIQUE INDEX uq_active_incoming_intervals_trip_day_seq "
        "ON active_incoming_intervals (raw_trip_id, service_date, stop_sequence)"
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
    op.execute(_CREATE_V2)
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
