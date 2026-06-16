"""Add integrated_terminus boolean to led_strip table.

Revision ID: 20260615_01
Revises: 20260614_01
Create Date: 2026-06-15
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260615_01"
down_revision: Union[str, None] = "20260614_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "led_strip",
        sa.Column("integrated_terminus", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("led_strip", "integrated_terminus")
