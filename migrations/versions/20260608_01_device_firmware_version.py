"""add current_firmware_version to esp32_device

Revision ID: 20260608_01
Revises: 20260607_02
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa

revision = '20260608_01'
down_revision = '20260607_02_device_settings'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'esp32_device',
        sa.Column('current_firmware_version', sa.String(50), nullable=True),
    )


def downgrade():
    op.drop_column('esp32_device', 'current_firmware_version')
