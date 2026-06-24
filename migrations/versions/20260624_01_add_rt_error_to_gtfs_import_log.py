"""Add rt_error_message and rt_error_at columns to gtfs_import_log.

Tracks the last real-time feed error per agency so the admin UI can surface
failures like quota exceeded, token expired, HTTP 4xx/5xx, etc.

Revision ID: 20260624_01
Revises: 20260623_03
Create Date: 2026-06-24
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20260624_01"
down_revision: Union[str, None] = "20260623_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("gtfs_import_log", sa.Column("rt_error_message", sa.Text(), nullable=True))
    op.add_column("gtfs_import_log", sa.Column("rt_error_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("gtfs_import_log", "rt_error_at")
    op.drop_column("gtfs_import_log", "rt_error_message")
