"""interval_system

Introduce the GTFS interval-based LED activation system in one step:

  - Widen stop.stop_id from VARCHAR(10) to VARCHAR(100)
  - Drop subagency table and line.subagency_id column
  - Drop legacy gtfs_trip table
  - Create raw_gtfs_trip (surrogate integer PK, canonical_trip_id FK)
  - Create raw_gtfs_stop_time (raw_trip_id FK, arrival/departure seconds,
    canonical_trip_stop_id, stop_id VARCHAR(100))
  - Create realtime_stop_time_override (GTFS-RT TripUpdates upsert target)
  - Create raw_gtfs_service_date (precomputed flat calendar rows)
  - Create active_incoming_intervals MATERIALIZED VIEW storing all today's
    LED intervals; time-window check done at query time in boardService

Revision ID: 20260525_interval_system
Revises: 20260522_02
Create Date: 2026-05-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260525_interval_system"
down_revision: Union[str, None] = "20260522_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ---------------------------------------------------------------------------
# Materialized view — stores all today's intervals; no NOW() filter baked in.
# The query in boardService applies EXTRACT(EPOCH FROM NOW()) at request time.
# ---------------------------------------------------------------------------
_MVIEW_SQL = """
CREATE MATERIALIZED VIEW active_incoming_intervals AS
WITH today_trips AS (
    SELECT rgt.id AS raw_trip_id
    FROM raw_gtfs_trip rgt
    JOIN raw_gtfs_service_date svc
      ON svc.service_id  = rgt.service_id
     AND svc.agency_name = rgt.agency_name
     AND svc.date        = TO_CHAR(CURRENT_DATE, 'YYYYMMDD')
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
),
with_effective AS (
    SELECT
        cs.canonical_trip_stop_id,
        cs.gtfs_trip_id,
        cs.agency_name,
        cs.stop_sequence,
        COALESCE(
            (SELECT ov.predicted_departure_ts
             FROM realtime_stop_time_override ov
             WHERE ov.gtfs_trip_id  = cs.gtfs_trip_id
               AND ov.agency_name   = cs.agency_name
               AND ov.stop_sequence = cs.prev_seq
               AND ov.start_date    = TO_CHAR(CURRENT_DATE, 'YYYYMMDD')
               AND (ov.schedule_relationship IS NULL OR ov.schedule_relationship != 1)
             LIMIT 1),
            EXTRACT(EPOCH FROM CURRENT_DATE)::bigint + cs.prev_dep_sec
        ) AS led_on_from,
        COALESCE(
            (SELECT ov.predicted_arrival_ts
             FROM realtime_stop_time_override ov
             WHERE ov.gtfs_trip_id  = cs.gtfs_trip_id
               AND ov.agency_name   = cs.agency_name
               AND ov.stop_sequence = cs.stop_sequence
               AND ov.start_date    = TO_CHAR(CURRENT_DATE, 'YYYYMMDD')
               AND (ov.schedule_relationship IS NULL OR ov.schedule_relationship != 1)
             LIMIT 1),
            EXTRACT(EPOCH FROM CURRENT_DATE)::bigint + cs.arrival_seconds
        ) AS led_on_until,
        NOT EXISTS (
            SELECT 1 FROM realtime_stop_time_override skip_ov
            WHERE skip_ov.gtfs_trip_id  = cs.gtfs_trip_id
              AND skip_ov.agency_name   = cs.agency_name
              AND skip_ov.stop_sequence = cs.stop_sequence
              AND skip_ov.start_date    = TO_CHAR(CURRENT_DATE, 'YYYYMMDD')
              AND skip_ov.schedule_relationship = 1
        ) AS not_skipped
    FROM canonical_stops cs
)
SELECT
    canonical_trip_stop_id,
    led_on_from,
    led_on_until
FROM with_effective
WHERE not_skipped
WITH NO DATA
"""

_DROP_MVIEW = "DROP MATERIALIZED VIEW IF EXISTS active_incoming_intervals"


def upgrade() -> None:
    # ── stop.stop_id: widen for long BMC stop IDs ───────────────────────────
    op.alter_column("stop", "stop_id",
                    existing_type=sa.String(10), type_=sa.String(100), nullable=False)

    # ── Drop subagency ───────────────────────────────────────────────────────
    op.drop_constraint("fk_line_subagency", "line", type_="foreignkey")
    op.drop_column("line", "subagency_id")
    op.drop_table("subagency")

    # ── raw_gtfs_trip ────────────────────────────────────────────────────────
    op.create_table(
        "raw_gtfs_trip",
        sa.Column("id",            sa.Integer(),   nullable=False, autoincrement=True),
        sa.Column("gtfs_trip_id",  sa.String(100), nullable=False),
        sa.Column("agency_name",   sa.String(100), nullable=False),
        sa.Column("route_id",      sa.String(50),  nullable=False),
        sa.Column("service_id",    sa.String(50),  nullable=False),
        sa.Column("direction_id",  sa.Integer(),   nullable=False, server_default="0"),
        sa.Column("shape_id",      sa.String(50),  nullable=True),
        sa.Column("trip_headsign", sa.String(200), nullable=True),
        sa.Column("canonical_trip_id", sa.Integer(),
                  sa.ForeignKey("trip.id"), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_raw_gtfs_trip"),
        sa.UniqueConstraint("gtfs_trip_id", "agency_name", name="uq_raw_gtfs_trip"),
        sa.ForeignKeyConstraint(["agency_name"], ["agency.name"]),
    )
    op.create_index("ix_raw_gtfs_trip_canonical", "raw_gtfs_trip", ["canonical_trip_id"])
    op.create_index("ix_raw_gtfs_trip_service",   "raw_gtfs_trip", ["service_id", "agency_name"])
    op.create_index("ix_raw_gtfs_trip_route",     "raw_gtfs_trip", ["route_id", "agency_name"])

    # ── raw_gtfs_stop_time ───────────────────────────────────────────────────
    op.create_table(
        "raw_gtfs_stop_time",
        sa.Column("id",           sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("raw_trip_id",  sa.Integer(), nullable=False),
        sa.Column("stop_sequence", sa.Integer(), nullable=False),
        sa.Column("stop_id",      sa.String(100), nullable=False),
        sa.Column("arrival_seconds",   sa.Integer(), nullable=True),
        sa.Column("departure_seconds", sa.Integer(), nullable=True),
        sa.Column("canonical_trip_stop_id", sa.Integer(),
                  sa.ForeignKey("trip_stop.id"), nullable=True),
        sa.UniqueConstraint(
            "raw_trip_id", "stop_sequence",
            name="uq_raw_gtfs_st_trip_seq",
        ),
        sa.ForeignKeyConstraint(
            ["raw_trip_id"], ["raw_gtfs_trip.id"],
            name="fk_raw_gtfs_st_trip",
        ),
    )
    op.create_index("ix_raw_gtfs_st_canonical", "raw_gtfs_stop_time", ["canonical_trip_stop_id"])
    op.create_index("ix_raw_gtfs_st_trip",      "raw_gtfs_stop_time", ["raw_trip_id"])
    op.create_index("ix_raw_gtfs_st_arr_sec",   "raw_gtfs_stop_time", ["arrival_seconds"])

    # ── realtime_stop_time_override ──────────────────────────────────────────
    op.create_table(
        "realtime_stop_time_override",
        sa.Column("id",            sa.Integer(),    primary_key=True, autoincrement=True),
        sa.Column("gtfs_trip_id",  sa.String(100),  nullable=False),
        sa.Column("agency_name",   sa.String(100),  nullable=False),
        sa.Column("start_date",    sa.String(8),    nullable=False),
        sa.Column("stop_sequence", sa.Integer(),    nullable=False),
        sa.Column("stop_id",       sa.String(100),  nullable=True),
        sa.Column("predicted_arrival_ts",   sa.BigInteger(), nullable=True),
        sa.Column("predicted_departure_ts", sa.BigInteger(), nullable=True),
        sa.Column("delay_seconds",          sa.Integer(),    nullable=True),
        sa.Column("schedule_relationship",  sa.Integer(),    nullable=True,
                  server_default="0"),
        sa.Column("feed_timestamp", sa.BigInteger(), nullable=True),
        sa.Column("updated_at",     sa.DateTime(),   nullable=False),
        sa.UniqueConstraint(
            "gtfs_trip_id", "agency_name", "start_date", "stop_sequence",
            name="uq_rt_override_trip_date_seq",
        ),
    )
    op.create_index(
        "ix_rt_override_trip_date",
        "realtime_stop_time_override",
        ["gtfs_trip_id", "agency_name", "start_date"],
    )
    op.create_index(
        "ix_rt_override_date",
        "realtime_stop_time_override",
        ["start_date", "agency_name"],
    )

    # ── Drop legacy gtfs_trip ────────────────────────────────────────────────
    op.drop_table("gtfs_trip")

    # ── raw_gtfs_service_date ────────────────────────────────────────────────
    op.create_table(
        "raw_gtfs_service_date",
        sa.Column("service_id",  sa.String(100), nullable=False),
        sa.Column("agency_name", sa.String(100), nullable=False),
        sa.Column("date",        sa.String(8),   nullable=False),
        sa.ForeignKeyConstraint(["agency_name"], ["agency.name"]),
        sa.PrimaryKeyConstraint("service_id", "agency_name", "date",
                                name="pk_raw_gtfs_service_date"),
    )
    op.create_index(
        "ix_raw_gtfs_service_date_today",
        "raw_gtfs_service_date",
        ["agency_name", "date"],
    )

    # ── active_incoming_intervals materialized view ──────────────────────────
    op.execute(_MVIEW_SQL)
    op.execute(
        "CREATE INDEX ix_active_incoming_intervals_ts_id "
        "ON active_incoming_intervals (canonical_trip_stop_id)"
    )
    op.execute(
        "CREATE INDEX ix_active_incoming_intervals_range "
        "ON active_incoming_intervals (led_on_from, led_on_until)"
    )


def downgrade() -> None:
    op.execute(_DROP_MVIEW)

    op.drop_index("ix_raw_gtfs_service_date_today", "raw_gtfs_service_date")
    op.drop_table("raw_gtfs_service_date")

    # Recreate gtfs_trip for rollback
    op.create_table(
        "gtfs_trip",
        sa.Column("id",      sa.String(100), nullable=False),
        sa.Column("trip_id", sa.Integer(),   nullable=False),
        sa.PrimaryKeyConstraint("id", "trip_id", name="pk_gtfs_trip_composite"),
        sa.ForeignKeyConstraint(["trip_id"], ["trip.id"]),
    )

    op.drop_table("realtime_stop_time_override")
    op.drop_table("raw_gtfs_stop_time")
    op.drop_table("raw_gtfs_trip")

    # Restore subagency
    op.create_table(
        "subagency",
        sa.Column("id",          sa.String(10),  nullable=False),
        sa.Column("name",        sa.String(100), nullable=False, unique=True),
        sa.Column("agency_name", sa.String(100), nullable=False),
        sa.ForeignKeyConstraint(["agency_name"], ["agency.name"]),
        sa.PrimaryKeyConstraint("id", "agency_name", name="pk_subagency_id_agency"),
    )
    op.add_column("line", sa.Column("subagency_id", sa.String(10), nullable=True))
    op.create_foreign_key(
        "fk_line_subagency",
        "line", "subagency",
        ["subagency_id", "agency_name"],
        ["id", "agency_name"],
    )

    op.alter_column("stop", "stop_id",
                    existing_type=sa.String(100), type_=sa.String(10), nullable=False)
