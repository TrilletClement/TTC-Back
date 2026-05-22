"""simplify_ota_schema

- firmware_package: drop app_name, app_version (and their unique constraint),
  rename package_file -> filename, add version (single string), add archived bool
- hardware: drop hardware_version, drop unique(type,version), add unique(type),
  rename default_firmware_package_id -> firmware_package_id
- drop hardware_firmware_assignment table entirely

Revision ID: 20260522_01
Revises: 20260519_04
Create Date: 2026-05-22
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '20260522_01'
down_revision: Union[str, None] = '20260519_04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── hardware_firmware_assignment → gone ──────────────────────────────────
    op.drop_table('hardware_firmware_assignment')

    # ── firmware_package ─────────────────────────────────────────────────────
    op.drop_constraint('uq_firmware_package_identity', 'firmware_package', type_='unique')
    op.alter_column('firmware_package', 'package_file', new_column_name='filename')
    op.drop_column('firmware_package', 'app_name')
    op.drop_column('firmware_package', 'app_version')
    op.drop_column('firmware_package', 'uploaded_by_user_id')
    op.add_column('firmware_package', sa.Column('version',  sa.String(50),  nullable=False, server_default=''))
    op.add_column('firmware_package', sa.Column('archived', sa.Boolean(),   nullable=False, server_default='false'))

    # ── hardware ─────────────────────────────────────────────────────────────
    # Deduplicate: for each hardware_type keep the row with a firmware set (or the lowest id).
    op.execute(sa.text("""
        DELETE FROM hardware h
        WHERE h.id NOT IN (
            SELECT DISTINCT ON (hardware_type)
                CASE WHEN default_firmware_package_id IS NOT NULL THEN id
                     ELSE (SELECT MIN(h2.id) FROM hardware h2 WHERE h2.hardware_type = h.hardware_type)
                END
            FROM hardware
        )
    """))

    op.drop_constraint('uq_hardware_type_version', 'hardware', type_='unique')
    op.drop_column('hardware', 'hardware_version')
    op.alter_column('hardware', 'default_firmware_package_id', new_column_name='firmware_package_id')
    op.create_unique_constraint('uq_hardware_type', 'hardware', ['hardware_type'])


def downgrade() -> None:
    op.drop_constraint('uq_hardware_type', 'hardware', type_='unique')
    op.alter_column('hardware', 'firmware_package_id', new_column_name='default_firmware_package_id')
    op.add_column('hardware', sa.Column('hardware_version', sa.String(100), nullable=False, server_default=''))
    op.create_unique_constraint('uq_hardware_type_version', 'hardware', ['hardware_type', 'hardware_version'])

    op.drop_column('firmware_package', 'archived')
    op.drop_column('firmware_package', 'version')
    op.add_column('firmware_package', sa.Column('uploaded_by_user_id', sa.Integer(), nullable=True))
    op.add_column('firmware_package', sa.Column('app_version', sa.String(50), nullable=False, server_default=''))
    op.add_column('firmware_package', sa.Column('app_name',   sa.String(100), nullable=False, server_default=''))
    op.alter_column('firmware_package', 'filename', new_column_name='package_file')
    op.create_unique_constraint('uq_firmware_package_identity', 'firmware_package', ['app_name', 'app_version'])

    op.create_table(
        'hardware_firmware_assignment',
        sa.Column('id',                  sa.Integer(),    primary_key=True),
        sa.Column('hardware_id',         sa.Integer(),    sa.ForeignKey('hardware.id'), nullable=False),
        sa.Column('firmware_name',       sa.String(100),  nullable=False),
        sa.Column('firmware_package_id', sa.Integer(),    sa.ForeignKey('firmware_package.id'), nullable=False),
        sa.Column('created_at',          sa.DateTime(),   nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('hardware_id', 'firmware_name', name='uq_hardware_firmware_assignment'),
    )
