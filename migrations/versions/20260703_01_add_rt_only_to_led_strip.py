"""Add led_strip.rt_only — opt-in "realtime only" mode per strip.

When enabled, a strip's LEDs light only on confirmed realtime data
(STIB vehicle_incoming, or an active interval whose trip is tracked in the
RT feed).  Theoretical schedule intervals no longer light the LED.
Default False keeps the current behaviour (schedule fallback lights LEDs).

Revision ID: 20260703_01
Revises: 20260625_01
Create Date: 2026-07-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260703_01"
down_revision: Union[str, None] = "20260625_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "led_strip",
        sa.Column("rt_only", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("led_strip", "rt_only")
