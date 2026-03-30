"""Add hardware firmware assignments keyed by hardware and firmware name

Revision ID: 20260328_01
Revises: 20260325_01
Create Date: 2026-03-28 22:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260328_01"
down_revision = "20260325_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hardware_firmware_assignment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("hardware_id", sa.Integer(), nullable=False),
        sa.Column("firmware_name", sa.String(length=100), nullable=False),
        sa.Column("firmware_package_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["firmware_package_id"], ["firmware_package.id"]),
        sa.ForeignKeyConstraint(["hardware_id"], ["hardware.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hardware_id", "firmware_name", name="uq_hardware_firmware_assignment"),
    )

    op.execute(
        sa.text(
            """
            INSERT INTO hardware_firmware_assignment (hardware_id, firmware_name, firmware_package_id, created_at)
            SELECT h.id, fp.app_name, fp.id, NOW()
            FROM hardware h
            JOIN firmware_package fp ON fp.id = h.default_firmware_package_id
            WHERE h.default_firmware_package_id IS NOT NULL
            ON CONFLICT (hardware_id, firmware_name)
            DO UPDATE SET firmware_package_id = EXCLUDED.firmware_package_id
            """
        )
    )


def downgrade() -> None:
    op.drop_table("hardware_firmware_assignment")
