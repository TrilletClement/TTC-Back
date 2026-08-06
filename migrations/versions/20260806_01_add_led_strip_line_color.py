"""Add per-strip line color override (visual route color, distinct from led_color).

Revision ID: 20260806_01
Revises: 20260803_03
Create Date: 2026-08-06
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260806_01"
down_revision: Union[str, None] = "20260803_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "led_strip",
        sa.Column("line_color", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("led_strip", "line_color")
