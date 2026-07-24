"""Add lat/lon coordinates to stop table.

Revision ID: 20260724_01
Revises: 20260722_01
Create Date: 2026-07-24
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260724_01"
down_revision: Union[str, None] = "20260722_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("stop", sa.Column("lat", sa.Float(), nullable=True))
    op.add_column("stop", sa.Column("lon", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("stop", "lon")
    op.drop_column("stop", "lat")
