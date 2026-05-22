"""drop_firmware_version

Remove version column from firmware_package — filename is now the sole identifier.

Revision ID: 20260522_02
Revises: 20260522_01
Create Date: 2026-05-22
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '20260522_02'
down_revision: Union[str, None] = '20260522_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('firmware_package', 'version')


def downgrade() -> None:
    op.add_column('firmware_package', sa.Column('version', sa.String(50), nullable=False, server_default=''))
