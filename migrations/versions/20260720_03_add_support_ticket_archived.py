"""add archived flag to support_ticket

Revision ID: 20260720_03
Revises: 20260720_02
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa

revision = '20260720_03'
down_revision = '20260720_02'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'support_ticket',
        sa.Column('archived', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column('support_ticket', 'archived')
