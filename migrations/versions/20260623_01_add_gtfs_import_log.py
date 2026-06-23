"""Add gtfs_import_log table to track per-operator static import status.

Revision ID: 20260623_01
Revises: 20260618_01
Create Date: 2026-06-23
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260623_01"
down_revision: Union[str, None] = "20260618_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gtfs_import_log",
        sa.Column("agency_name", sa.String(50), primary_key=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="never"),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("gtfs_import_log")
