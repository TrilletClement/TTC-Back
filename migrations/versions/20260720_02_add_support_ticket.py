"""add support_ticket table

Revision ID: 20260720_02
Revises: 20260720_01
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa

revision = '20260720_02'
down_revision = '20260720_01'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'support_ticket',
        sa.Column('id',          sa.Integer(),   nullable=False, autoincrement=True),
        sa.Column('user_id',     sa.Integer(),   nullable=False),
        sa.Column('order_id',    sa.Integer(),   nullable=True),
        sa.Column('subject',     sa.String(200), nullable=False),
        sa.Column('message',     sa.Text(),      nullable=False),
        sa.Column('status',      sa.String(20),  nullable=False, server_default='open'),
        sa.Column('admin_reply', sa.Text(),      nullable=True),
        sa.Column('replied_at',  sa.DateTime(),  nullable=True),
        sa.Column('created_at',  sa.DateTime(),  nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'],  ['user.id']),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id']),
    )


def downgrade():
    op.drop_table('support_ticket')
