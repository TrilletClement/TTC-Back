"""add device settings — json_settings on hardware, json_settings_override + last_settings_updated_at on esp32_device

Revision ID: 20260607_02_device_settings
Revises: 20260607_01_board_type_not_null
Create Date: 2026-06-07
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260607_02_device_settings"
down_revision: Union[str, tuple] = "20260607_01_board_type_not_null"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Mirrors LEDController::default_color_tuning() from led_controller.cpp,
# plus the device operating mode consumed by the ESP firmware.
DEFAULT_SETTINGS = {
    "sections": [
        {
            "key": "device",
            "label": "Device",
            "settings": [
                {
                    "key": "mode",
                    "label": "Operating mode",
                    "type": "enum",
                    "options": ["production", "field"],
                    "default": "production",
                },
            ],
        },
        {
            "key": "leds",
            "label": "LED Tuning",
            "settings": [
                {"key": "light_intensity_percent", "label": "Light intensity",        "type": "percentage", "default": 100.0},
                {"key": "gamma",                   "label": "Gamma value",            "type": "float",      "default": 2.2},
                {"key": "enable_gamma",            "label": "Enable gamma correction","type": "boolean",    "default": True},
                {"key": "use_ws2812_gamma_lut",    "label": "Use WS2812 gamma LUT",  "type": "boolean",    "default": False},
                {"key": "red_balance_percent",     "label": "Red balance",            "type": "percentage", "default": 100.0},
                {"key": "green_balance_percent",   "label": "Green balance",          "type": "percentage", "default": 100.0},
                {"key": "blue_balance_percent",    "label": "Blue balance",           "type": "percentage", "default": 100.0},
                {"key": "enable_balance",          "label": "Enable RGB balance",     "type": "boolean",    "default": False},
                {"key": "enable_normalization",    "label": "Enable normalization",   "type": "boolean",    "default": False},
                {"key": "enable_clamp",            "label": "Enable clamp",           "type": "boolean",    "default": False},
            ],
        },
    ]
}

DEFAULT_SETTINGS_JSON = json.dumps(DEFAULT_SETTINGS)


def upgrade() -> None:
    op.add_column("hardware", sa.Column("json_settings", sa.Text(), nullable=True))
    op.add_column("esp32_device", sa.Column("json_settings_override", sa.Text(), nullable=True))
    op.add_column("esp32_device", sa.Column("last_settings_updated_at", sa.DateTime(), nullable=True))

    conn = op.get_bind()

    # Seed all existing hardware types with the default settings schema.
    conn.execute(
        sa.text("UPDATE hardware SET json_settings = :js WHERE json_settings IS NULL"),
        {"js": DEFAULT_SETTINGS_JSON},
    )

    # Existing devices inherit hardware defaults — no per-device override needed.
    # Stamp last_settings_updated_at = NOW() so that the ledstrips response
    # immediately carries a non-null timestamp.  The ESP has no matching value
    # in NVS yet, so it will fetch /api/esp/settings on its very next poll and
    # apply the hardware defaults.
    conn.execute(
        sa.text(
            "UPDATE esp32_device"
            " SET last_settings_updated_at = NOW()"
            " WHERE last_settings_updated_at IS NULL"
        )
    )


def downgrade() -> None:
    op.drop_column("hardware", "json_settings")
    op.drop_column("esp32_device", "json_settings_override")
    op.drop_column("esp32_device", "last_settings_updated_at")
