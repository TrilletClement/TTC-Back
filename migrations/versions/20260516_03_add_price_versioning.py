"""add_price_versioning

Creates price_version and board_type_price tables for versioned pricing.
Seeds an initial price version with prices for the two existing board types.
Adds price_version_id (nullable) to the orders table so each order records
which price catalogue was in effect at creation time.

Revision ID: 20260516_03
Revises: 20260516_02
Create Date: 2026-05-16

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column, select

revision: str = '20260516_03'
down_revision: Union[str, None] = '20260516_02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── price_version ────────────────────────────────────────────────────────
    op.create_table(
        'price_version',
        sa.Column('id',         sa.Integer(),     primary_key=True),
        sa.Column('label',      sa.String(100),   nullable=True),
        sa.Column('created_at', sa.DateTime(),    nullable=False, server_default=sa.func.now()),
    )

    # ── board_type_price ─────────────────────────────────────────────────────
    op.create_table(
        'board_type_price',
        sa.Column('id',                  sa.Integer(), primary_key=True),
        sa.Column('price_version_id',    sa.Integer(), sa.ForeignKey('price_version.id'), nullable=False),
        sa.Column('board_type_id',       sa.Integer(), sa.ForeignKey('board_type.id'),    nullable=False),
        sa.Column('base_price_cents',    sa.Integer(), nullable=False),
        sa.Column('reduced_price_cents', sa.Integer(), nullable=False),
        sa.UniqueConstraint('price_version_id', 'board_type_id', name='uq_price_version_board_type'),
    )

    # ── Seed initial price version ───────────────────────────────────────────
    conn = op.get_bind()

    conn.execute(
        sa.text("INSERT INTO price_version (label, created_at) VALUES ('v1 - initial', NOW())")
    )
    version_id = conn.execute(sa.text("SELECT id FROM price_version ORDER BY id DESC LIMIT 1")).scalar()

    board_type_t = table('board_type', column('id', sa.Integer), column('name', sa.String))
    rows = conn.execute(select(board_type_t.c.id, board_type_t.c.name)).fetchall()

    seed_prices = {
        'Small Frame': (2999, 1999),
        'Big Frame':   (4999, 3499),
    }
    for bt_id, bt_name in rows:
        base, reduced = seed_prices.get(bt_name, (0, 0))
        conn.execute(sa.text(
            "INSERT INTO board_type_price (price_version_id, board_type_id, base_price_cents, reduced_price_cents) "
            "VALUES (:vid, :btid, :base, :reduced)"
        ), {"vid": version_id, "btid": bt_id, "base": base, "reduced": reduced})

    # ── orders: record which price version was active at order time ──────────
    op.add_column(
        'orders',
        sa.Column('price_version_id', sa.Integer(), sa.ForeignKey('price_version.id'), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('orders', 'price_version_id')
    op.drop_table('board_type_price')
    op.drop_table('price_version')
