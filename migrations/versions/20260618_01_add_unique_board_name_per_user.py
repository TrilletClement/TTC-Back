"""add unique board name per user (partial index on active boards)

Revision ID: 20260618_01
Revises: 20260617_01
Create Date: 2026-06-18

"""

from alembic import op

revision = "20260618_01"
down_revision = "20260617_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX uq_board_owner_name_active
        ON board (owner_id, lower(name))
        WHERE archived = false
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_board_owner_name_active")
