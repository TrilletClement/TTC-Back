"""Add custom_subname string to led table.

Revision ID: 20260616_01
Revises: 20260615_01
Create Date: 2026-06-16
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260616_01"
down_revision: Union[str, None] = "20260615_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "led",
        sa.Column("custom_subname", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("led", "custom_subname")
