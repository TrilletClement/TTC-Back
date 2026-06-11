"""add tracking_url to orders

Revision ID: 20260610_03
Revises: 20260610_02
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa

revision = '20260610_03'
down_revision = '20260610_02'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('orders', sa.Column('tracking_url', sa.String(500), nullable=True))


def downgrade():
    op.drop_column('orders', 'tracking_url')
