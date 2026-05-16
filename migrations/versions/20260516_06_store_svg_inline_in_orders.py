"""store_svg_inline_in_orders

Replace svg_path (filesystem pointer) with svg_content (TEXT) in the orders
table. SVGs are small (10-50 KB) so inline storage is simpler and keeps the
data self-contained.

Revision ID: 20260516_06
Revises: 20260516_05
Create Date: 2026-05-16

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '20260516_06'
down_revision: Union[str, None] = '20260516_05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('orders', 'svg_path')
    op.add_column('orders', sa.Column('svg_content', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('orders', 'svg_content')
    op.add_column('orders', sa.Column('svg_path', sa.String(255), nullable=True))
