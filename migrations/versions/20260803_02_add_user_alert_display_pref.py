"""Add per-user alert display preference.

Revision ID: 20260803_02
Revises: 20260803_01
Create Date: 2026-08-03
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260803_02"
down_revision: Union[str, None] = "20260803_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column("alert_display_pref", sa.String(10), nullable=False, server_default="banner"),
    )


def downgrade() -> None:
    op.drop_column("user", "alert_display_pref")
