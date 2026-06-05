"""Widen cert_serial from bigint to numeric(40) to fit X.509 160-bit serials.

Revision ID: 20260605_01_cert_serial_bigint_to_numeric
Revises: 20260603_01_add_device_certificate
Create Date: 2026-06-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260605_01_cert_serial_bigint_to_numeric"
down_revision: Union[str, None] = "20260603_01_add_device_certificate"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "device_certificate", "cert_serial",
        existing_type=sa.BigInteger(),
        type_=sa.Numeric(scale=0),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "device_certificate", "cert_serial",
        existing_type=sa.Numeric(scale=0),
        type_=sa.BigInteger(),
        existing_nullable=False,
    )
