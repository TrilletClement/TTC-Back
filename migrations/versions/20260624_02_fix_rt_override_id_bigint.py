"""Change realtime_stop_time_override.id from INTEGER to BIGINT.

The INT4 sequence (max 2,147,483,647) was exhausted because PostgreSQL
calls nextval() on every INSERT even when ON CONFLICT DO UPDATE fires,
consuming ~5000 sequence values per RT update cycle (every 30 s).

Revision ID: 20260624_02
Revises: 20260624_01
Create Date: 2026-06-24
"""
from typing import Sequence, Union
from alembic import op

revision: str = "20260624_02"
down_revision: Union[str, None] = "20260624_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE realtime_stop_time_override ALTER COLUMN id TYPE BIGINT"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE realtime_stop_time_override ALTER COLUMN id TYPE INTEGER"
    )
