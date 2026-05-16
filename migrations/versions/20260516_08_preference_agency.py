"""add_preferred_agency_to_user

Revision ID: 20260516_08
Revises: 20260516_07
Create Date: 2026-05-16

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '20260516_08'
down_revision: Union[str, None] = '20260516_07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('user', sa.Column('preferred_agency', sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column('user', 'preferred_agency')