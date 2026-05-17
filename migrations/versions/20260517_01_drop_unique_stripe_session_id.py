"""drop unique stripe_session_id

Revision ID: 20260517_01
Revises: 20260516_08
Create Date: 2026-05-17 20:06:59.221925

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20260517_01'
down_revision: Union[str, None] = '20260516_08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.drop_constraint('orders_stripe_session_id_key', 'orders', type_='unique')

def downgrade() -> None:
    op.create_unique_constraint('orders_stripe_session_id_key', 'orders', ['stripe_session_id'])
