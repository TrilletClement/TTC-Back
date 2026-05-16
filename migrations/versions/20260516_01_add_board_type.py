"""add_board_type

Revision ID: 20260516_01
Revises: bb1f31bb2aa6
Create Date: 2026-05-16

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '20260516_01'
down_revision: Union[str, None] = 'bb1f31bb2aa6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

board_type_table = sa.table(
    'board_type',
    sa.column('id', sa.Integer),
    sa.column('name', sa.String),
    sa.column('max_led', sa.Integer),
    sa.column('max_ledstrip', sa.Integer),
)


def upgrade() -> None:
    op.create_table(
        'board_type',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('max_led', sa.Integer(), nullable=False),
        sa.Column('max_ledstrip', sa.Integer(), nullable=False),
    )

    op.bulk_insert(board_type_table, [
        {'name': 'Small Frame', 'max_led': 10, 'max_ledstrip': 2},
        {'name': 'Big Frame',   'max_led': 16, 'max_ledstrip': 4},
    ])

    op.add_column(
        'board',
        sa.Column('board_type_id', sa.Integer(), sa.ForeignKey('board_type.id'), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('board', 'board_type_id')
    op.drop_table('board_type')
