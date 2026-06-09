"""add esp_device_id to orders

Revision ID: 20260609_01
Revises: 20260608_02
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa

revision = '20260609_01'
down_revision = '20260608_02'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'orders',
        sa.Column('esp_device_id', sa.Integer(), sa.ForeignKey('esp32_device.id'), nullable=True),
    )


def downgrade():
    op.drop_column('orders', 'esp_device_id')
