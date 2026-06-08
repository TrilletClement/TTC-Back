"""add OTA partition status columns to esp32_device

Revision ID: 20260608_02
Revises: 20260608_01
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa

revision = '20260608_02'
down_revision = '20260608_01'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('esp32_device', sa.Column('running_partition', sa.String(20), nullable=True))
    op.add_column('esp32_device', sa.Column('boot_partition',    sa.String(20), nullable=True))
    op.add_column('esp32_device', sa.Column('update_partition',  sa.String(20), nullable=True))
    op.add_column('esp32_device', sa.Column('ota_state',         sa.String(20), nullable=True))


def downgrade():
    op.drop_column('esp32_device', 'ota_state')
    op.drop_column('esp32_device', 'update_partition')
    op.drop_column('esp32_device', 'boot_partition')
    op.drop_column('esp32_device', 'running_partition')
