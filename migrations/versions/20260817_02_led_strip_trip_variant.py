"""Add led_strip.trip_0_id / trip_1_id branch overrides.

Some lines (e.g. TEC tram T1 in Liège) split into several branches with
different termini that share the same GTFS direction_id — GTFS import
already creates one canonical Trip per distinct stop sequence, but only one
"best" Trip per (line, direction) is reachable via Line.best_trip_0_id /
best_trip_1_id. These new columns let a LedStrip pin itself to a specific
branch instead of always following the line's best trip. NULL (the default
for every existing row) means "keep following the line's best trip" — fully
backward compatible, no backfill needed.

ondelete="SET NULL" matters here: GTFS import's orphan-trip cleanup does a
bulk DELETE on Trip that bypasses ORM cascades, so the DB-level FK is what
protects a saved strip from pointing at a deleted trip — it just reverts to
NULL (falls back to best_trip) instead of erroring.

Revision ID: 20260817_02
Revises: 20260817_01
Create Date: 2026-08-17
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260817_02"
down_revision: Union[str, None] = "20260817_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("led_strip", sa.Column("trip_0_id", sa.Integer(), nullable=True))
    op.add_column("led_strip", sa.Column("trip_1_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_led_strip_trip_0_id", "led_strip", "trip", ["trip_0_id"], ["id"], ondelete="SET NULL"
    )
    op.create_foreign_key(
        "fk_led_strip_trip_1_id", "led_strip", "trip", ["trip_1_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint("fk_led_strip_trip_0_id", "led_strip", type_="foreignkey")
    op.drop_constraint("fk_led_strip_trip_1_id", "led_strip", type_="foreignkey")
    op.drop_column("led_strip", "trip_0_id")
    op.drop_column("led_strip", "trip_1_id")
