"""Refactor led strip mapping into led table

Revision ID: 20260310_01
Revises: 20260210_01
Create Date: 2026-03-10 21:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260310_01"
down_revision = "20260210_01"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    op.add_column("led", sa.Column("ledstrip_id", sa.Integer(), nullable=True))
    op.add_column("led", sa.Column("ledstrip_index", sa.Integer(), nullable=True))
    op.add_column("led", sa.Column("led_color", sa.String(length=50), nullable=True, server_default="#00FF00"))

    op.create_foreign_key("fk_led_ledstrip_id", "led", "led_strip", ["ledstrip_id"], ["id"])

    for i in range(1, 13):
        conn.execute(
            sa.text(
                f"""
                UPDATE led
                SET
                    ledstrip_id = ls.id,
                    ledstrip_index = :idx,
                    led_color = COALESCE(
                        CASE
                            WHEN ln.color ~* '^#?[0-9a-f]{6}$' THEN '#' || UPPER(REPLACE(ln.color, '#', ''))
                            ELSE NULL
                        END,
                        '#00FF00'
                    )
                FROM led_strip ls
                LEFT JOIN line ln
                       ON ln.id = ls.line_id
                      AND ln.agency_name = ls.line_agency_name
                WHERE led.id = ls.led{i}
                """
            ),
            {"idx": i},
        )

    op.execute(sa.text("UPDATE led SET led_color = '#00FF00' WHERE led_color IS NULL"))

    op.alter_column("led", "ledstrip_id", nullable=False)
    op.alter_column("led", "ledstrip_index", nullable=False)
    op.alter_column("led", "led_color", nullable=False, server_default="#00FF00")

    op.create_index("ix_led_ledstrip_index", "led", ["ledstrip_index"], unique=False)
    op.create_unique_constraint("uq_led_ledstrip_id_index", "led", ["ledstrip_id", "ledstrip_index"])

    for i in range(1, 13):
        op.drop_column("led_strip", f"led{i}")
    op.drop_column("led_strip", "led_color")


def downgrade():
    conn = op.get_bind()

    op.add_column("led_strip", sa.Column("led_color", sa.String(length=50), nullable=False, server_default="red"))
    for i in range(1, 13):
        op.add_column("led_strip", sa.Column(f"led{i}", sa.Integer(), nullable=True))
        op.create_foreign_key(f"fk_led_strip_led{i}", "led_strip", "led", [f"led{i}"], ["id"])

    op.execute(sa.text("UPDATE led_strip SET led_color = 'red' WHERE led_color IS NULL"))

    for i in range(1, 13):
        conn.execute(
            sa.text(
                f"""
                UPDATE led_strip ls
                SET led{i} = led.id
                FROM led
                WHERE led.ledstrip_id = ls.id
                  AND led.ledstrip_index = :idx
                """
            ),
            {"idx": i},
        )

    op.drop_constraint("uq_led_ledstrip_id_index", "led", type_="unique")
    op.drop_index("ix_led_ledstrip_index", table_name="led")
    op.drop_constraint("fk_led_ledstrip_id", "led", type_="foreignkey")

    op.drop_column("led", "led_color")
    op.drop_column("led", "ledstrip_index")
    op.drop_column("led", "ledstrip_id")
