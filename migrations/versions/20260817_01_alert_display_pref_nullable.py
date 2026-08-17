"""Make user.alert_display_pref nullable.

NULL now means "no explicit preference set" (falls back to 'banner' at the
application layer), distinct from a user explicitly choosing 'banner' —
previously NOT NULL + server_default baked 'banner' into every row at
creation time, so there was no way to tell the two apart, and no way to
change the app-wide default retroactively for users who never touched the
setting. Mirrors how preferred_agency already works.

Revision ID: 20260817_01
Revises: 20260816_01
Create Date: 2026-08-17
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260817_01"
down_revision: Union[str, None] = "20260816_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "user",
        "alert_display_pref",
        existing_type=sa.String(10),
        nullable=True,
        server_default=None,
    )


def downgrade() -> None:
    op.execute("UPDATE \"user\" SET alert_display_pref = 'banner' WHERE alert_display_pref IS NULL")
    op.alter_column(
        "user",
        "alert_display_pref",
        existing_type=sa.String(10),
        nullable=False,
        server_default="banner",
    )
