"""Add custom_terminus_left_name and custom_terminus_right_name to led_strip.

Revision ID: 20260617_01
Revises: 20260616_01
Create Date: 2026-06-17
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260617_01"
down_revision: Union[str, None] = "20260616_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "led_strip",
        sa.Column("custom_terminus_left_name", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "led_strip",
        sa.Column("custom_terminus_right_name", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("led_strip", "custom_terminus_right_name")
    op.drop_column("led_strip", "custom_terminus_left_name")
