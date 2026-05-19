"""add google_id and nullable password to users

Revision ID: 20260519_01
Revises: 20260517_01
Create Date: 2026-05-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '20260519_01'
down_revision: Union[str, None] = '20260517_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.alter_column('user', 'password',
        existing_type=sa.String(),
        nullable=True
    )
    op.add_column('user', sa.Column('google_id', sa.String(), nullable=True))
    op.create_unique_constraint('user_google_id_key', 'user', ['google_id'])
    op.create_index('ix_user_google_id', 'user', ['google_id'], unique=True)

def downgrade() -> None:
    op.drop_index('ix_user_google_id', table_name='user')
    op.drop_constraint('user_google_id_key', 'user', type_='unique')
    op.drop_column('user', 'google_id')
    op.alter_column('user', 'password',
        existing_type=sa.String(),
        nullable=False
    )