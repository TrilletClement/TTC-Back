"""Add ON DELETE CASCADE to trip_stop_led_link.trip_stop_id FK.

During GTFS static re-import, old trip_stop rows are deleted before
_rebuild_trip_stop_led_links can remap the links. The FK constraint
blocked the deletion. With CASCADE, the link rows are deleted automatically
and the rebuild recreates them pointing to the new trip_stop ids.

Revision ID: 20260624_03
Revises: 20260624_02
Create Date: 2026-06-24
"""
from typing import Sequence, Union
from alembic import op

revision: str = "20260624_03"
down_revision: Union[str, None] = "20260624_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "trip_stop_led_link_trip_stop_id_fkey",
        "trip_stop_led_link",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "trip_stop_led_link_trip_stop_id_fkey",
        "trip_stop_led_link",
        "trip_stop",
        ["trip_stop_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "trip_stop_led_link_trip_stop_id_fkey",
        "trip_stop_led_link",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "trip_stop_led_link_trip_stop_id_fkey",
        "trip_stop_led_link",
        "trip_stop",
        ["trip_stop_id"],
        ["id"],
    )
