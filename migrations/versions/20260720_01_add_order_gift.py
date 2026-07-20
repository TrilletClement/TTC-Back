"""add order_gift table for gifted orders

Revision ID: 20260720_01
Revises: 20260719_01
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa

revision = '20260720_01'
down_revision = '20260719_01'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'order_gift',
        sa.Column('id',                  sa.Integer(),    nullable=False, autoincrement=True),
        sa.Column('order_id',            sa.Integer(),    nullable=False),
        sa.Column('recipient_name',      sa.String(200),  nullable=False),
        sa.Column('recipient_email',     sa.String(255),  nullable=False),
        sa.Column('message',             sa.Text(),       nullable=True),
        sa.Column('claim_token',         sa.String(64),   nullable=True),
        sa.Column('claim_token_expiry',  sa.DateTime(),   nullable=True),
        sa.Column('claimed_at',          sa.DateTime(),   nullable=True),
        sa.Column('claimed_by_user_id',  sa.Integer(),    nullable=True),
        sa.Column('created_at',          sa.DateTime(),   nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['order_id'],           ['orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['claimed_by_user_id'], ['user.id']),
        sa.UniqueConstraint('order_id'),
        sa.UniqueConstraint('claim_token'),
    )


def downgrade():
    op.drop_table('order_gift')
