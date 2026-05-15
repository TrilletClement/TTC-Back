"""add_board_archived_column

Revision ID: bb1f31bb2aa6
Revises: 20260419_01
Create Date: 2026-05-15

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'bb1f31bb2aa6'
down_revision: Union[str, None] = '20260419_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('board', sa.Column('archived', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    op.drop_column('board', 'archived')
