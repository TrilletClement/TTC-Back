"""add_tracking_number_to_orders

Revision ID: 20260516_07
Revises: 20260516_06
Create Date: 2026-05-16

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '20260516_07'
down_revision: Union[str, None] = '20260516_06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('tracking_number', sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column('orders', 'tracking_number')
