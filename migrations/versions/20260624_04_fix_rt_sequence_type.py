"""Fix realtime_stop_time_override_id_seq sequence type to BIGINT.

ALTER COLUMN id TYPE BIGINT (migration 20260624_02) changed the column type
but left the PostgreSQL sequence typed as INTEGER with maxvalue = 2147483647.
The sequence was already exhausted, so every RT upsert still fails with
SequenceGeneratorLimitExceeded.

This migration changes the sequence type to BIGINT and restarts it at
2147483648 (the first value that cannot collide with any existing INT4 row).

Revision ID: 20260624_04
Revises: 20260624_03
Create Date: 2026-06-24
"""
from typing import Sequence, Union
from alembic import op

revision: str = "20260624_04"
down_revision: Union[str, None] = "20260624_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER SEQUENCE realtime_stop_time_override_id_seq "
        "AS bigint MAXVALUE 9223372036854775807 RESTART WITH 2147483648"
    )


def downgrade() -> None:
    op.execute(
        "ALTER SEQUENCE realtime_stop_time_override_id_seq "
        "AS integer MAXVALUE 2147483647 RESTART WITH 1"
    )
