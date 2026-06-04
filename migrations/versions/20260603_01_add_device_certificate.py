"""Add device_certificate table and make esp32_device.owner_id nullable.

Revision ID: 20260603_01_add_device_certificate
Revises: 20260529_01_widen_gtfs_trip_id
Create Date: 2026-06-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260603_01_add_device_certificate"
down_revision: Union[str, None] = "20260529_01_widen_gtfs_trip_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make owner_id nullable so devices can be created without a linked user
    # (manufactured before being sold / assigned to a customer).
    op.alter_column(
        "esp32_device", "owner_id",
        existing_type=sa.Integer(),
        nullable=True,
    )

    # Device X.509 certificate table.
    op.create_table(
        "device_certificate",
        sa.Column("id",                     sa.Integer(),    primary_key=True),
        sa.Column("esp32_device_id",        sa.Integer(),    sa.ForeignKey("esp32_device.id"), nullable=False),
        sa.Column("mac_address",            sa.String(17),   nullable=False),
        sa.Column("cert_serial",            sa.BigInteger(), nullable=False, unique=True),
        sa.Column("cert_subject",           sa.String(255),  nullable=False),
        sa.Column("cert_fingerprint_sha256",sa.String(64),   nullable=False, unique=True),
        sa.Column("cert_pem",               sa.Text(),       nullable=False),
        sa.Column("issued_at",              sa.DateTime(),   nullable=False),
        sa.Column("expires_at",             sa.DateTime(),   nullable=False),
        sa.Column("revoked_at",             sa.DateTime(),   nullable=True),
        sa.Column("revocation_reason",      sa.String(255),  nullable=True),
        sa.Column("last_seen_at",           sa.DateTime(),   nullable=True),
    )
    op.create_index("ix_device_certificate_esp32_device_id", "device_certificate", ["esp32_device_id"])
    op.create_index("ix_device_certificate_mac_address",     "device_certificate", ["mac_address"])
    op.create_index("ix_device_certificate_fingerprint",     "device_certificate", ["cert_fingerprint_sha256"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_device_certificate_fingerprint",    table_name="device_certificate")
    op.drop_index("ix_device_certificate_mac_address",    table_name="device_certificate")
    op.drop_index("ix_device_certificate_esp32_device_id",table_name="device_certificate")
    op.drop_table("device_certificate")

    # Revert owner_id to non-nullable (only safe if no NULL rows exist).
    op.alter_column(
        "esp32_device", "owner_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
