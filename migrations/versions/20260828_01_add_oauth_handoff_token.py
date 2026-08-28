"""add oauth handoff token

Revision ID: 20260828_01
Revises: 20260817_03
Create Date: 2026-08-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20260828_01'
down_revision: Union[str, None] = '20260817_03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('user', sa.Column('oauth_handoff_token', sa.String(length=100), nullable=True))
    op.add_column('user', sa.Column('oauth_handoff_token_expiry', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('user', 'oauth_handoff_token_expiry')
    op.drop_column('user', 'oauth_handoff_token')
