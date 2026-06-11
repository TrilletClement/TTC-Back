"""simplify shipping_option_config to just option_code

Revision ID: 20260611_03
Revises: 20260611_02
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa

revision = '20260611_03'
down_revision = '20260611_02'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column('shipping_option_config', 'enabled')
    op.drop_column('shipping_option_config', 'display_order')


def downgrade():
    op.add_column('shipping_option_config', sa.Column('enabled',       sa.Boolean, nullable=False, server_default='true'))
    op.add_column('shipping_option_config', sa.Column('display_order', sa.Integer, nullable=False, server_default='0'))
