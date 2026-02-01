"""Create order table

Revision ID: 20240909_03
Revises: 20240909_02
Create Date: 2024-09-09
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20240909_03'
down_revision = '20240909_02'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'order',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('board_id', sa.Integer(), sa.ForeignKey('board.id'), nullable=False),
        sa.Column('svg_path', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('details', sa.String(length=500), nullable=True),
        sa.Column('led_colors', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False)
    )


def downgrade():
    op.drop_table('order')
