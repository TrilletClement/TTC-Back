"""Add OTA firmware packages, hardware config, and device overrides

Revision ID: 20260325_01
Revises: 7ebc7ced8edf
Create Date: 2026-03-25 22:00:00.000000
"""

import json
from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "20260325_01"
down_revision = "7ebc7ced8edf"
branch_labels = None
depends_on = None


def _load_legacy_version_config():
    config_path = Path(__file__).resolve().parents[2] / "static" / "package-version.json"
    if not config_path.exists():
        return None

    with config_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _ensure_package(conn, app_name: str, app_version: str, package_file: str):
    existing_id = conn.execute(
        sa.text("SELECT id FROM firmware_package WHERE package_file = :package_file"),
        {"package_file": package_file},
    ).scalar()
    if existing_id:
        return existing_id

    return conn.execute(
        sa.text(
            """
            INSERT INTO firmware_package (app_name, app_version, package_file, created_at)
            VALUES (:app_name, :app_version, :package_file, now())
            RETURNING id
            """
        ),
        {
            "app_name": app_name,
            "app_version": app_version,
            "package_file": package_file,
        },
    ).scalar_one()


def upgrade():
    op.create_table(
        "firmware_package",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("app_name", sa.String(length=100), nullable=False),
        sa.Column("app_version", sa.String(length=50), nullable=False),
        sa.Column("package_file", sa.String(length=255), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("package_file"),
        sa.UniqueConstraint("app_name", "app_version", name="uq_firmware_package_identity"),
    )

    op.create_table(
        "hardware",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("hardware_type", sa.String(length=100), nullable=False),
        sa.Column("hardware_version", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("default_firmware_package_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["default_firmware_package_id"], ["firmware_package.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hardware_type", "hardware_version", name="uq_hardware_type_version"),
    )

    op.add_column("esp32_device", sa.Column("hardware_id", sa.Integer(), nullable=True))
    op.add_column("esp32_device", sa.Column("current_firmware_id", sa.Integer(), nullable=True))
    op.add_column("esp32_device", sa.Column("target_firmware_id", sa.Integer(), nullable=True))
    op.add_column("esp32_device", sa.Column("last_ota_check", sa.DateTime(), nullable=True))
    op.drop_column("esp32_device", "version_firmware")
    op.drop_column("esp32_device", "version_soft")
    op.drop_column("esp32_device", "version_hard")
    op.create_foreign_key(
        "fk_esp32_device_hardware_id",
        "esp32_device",
        "hardware",
        ["hardware_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_esp32_device_current_firmware_id",
        "esp32_device",
        "firmware_package",
        ["current_firmware_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_esp32_device_target_firmware_id",
        "esp32_device",
        "firmware_package",
        ["target_firmware_id"],
        ["id"],
    )

    conn = op.get_bind()
    legacy = _load_legacy_version_config() or {}

    for hardware_type, entry in legacy.get("default", {}).items():
        app_version = (entry or {}).get("app_version")
        package_file = (entry or {}).get("package_file")
        if not app_version or not package_file:
            continue

        package_id = _ensure_package(conn, app_name=hardware_type, app_version=app_version, package_file=package_file)
        conn.execute(
            sa.text(
                """
                INSERT INTO hardware (hardware_type, hardware_version, default_firmware_package_id, created_at)
                VALUES (:hardware_type, '', :package_id, now())
                ON CONFLICT (hardware_type, hardware_version)
                DO UPDATE SET default_firmware_package_id = EXCLUDED.default_firmware_package_id
                """
            ),
            {
                "hardware_type": hardware_type,
                "package_id": package_id,
            },
        )

    for mac_address, entry in legacy.get("exceptions", {}).items():
        app_version = (entry or {}).get("app_version")
        package_file = (entry or {}).get("package_file")
        if not app_version or not package_file:
            continue

        package_id = _ensure_package(conn, app_name="legacy-exception", app_version=app_version, package_file=package_file)
        conn.execute(
            sa.text(
                """
                UPDATE esp32_device
                SET target_firmware_id = :package_id
                WHERE lower(mac_address) = lower(:mac_address)
                """
            ),
            {
                "package_id": package_id,
                "mac_address": mac_address,
            },
        )


def downgrade():
    op.drop_constraint("fk_esp32_device_target_firmware_id", "esp32_device", type_="foreignkey")
    op.drop_constraint("fk_esp32_device_current_firmware_id", "esp32_device", type_="foreignkey")
    op.drop_constraint("fk_esp32_device_hardware_id", "esp32_device", type_="foreignkey")
    op.add_column("esp32_device", sa.Column("version_hard", sa.String(length=50), nullable=True))
    op.add_column("esp32_device", sa.Column("version_soft", sa.String(length=50), nullable=True))
    op.add_column("esp32_device", sa.Column("version_firmware", sa.String(length=50), nullable=True))
    op.drop_column("esp32_device", "last_ota_check")
    op.drop_column("esp32_device", "target_firmware_id")
    op.drop_column("esp32_device", "current_firmware_id")
    op.drop_column("esp32_device", "hardware_id")
    op.drop_table("hardware")
    op.drop_table("firmware_package")
