"""Add subagency_id to line and FK to subagency

Revision ID: 20240909_06
Revises: 20240909_05
Create Date: 2024-09-09 00:00:06.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20240909_06'
down_revision = '20240909_05'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # Add column if missing
    existing_cols = {col["name"] for col in insp.get_columns("line")}
    if "subagency_id" not in existing_cols:
        op.add_column("line", sa.Column("subagency_id", sa.String(length=10), nullable=True))

    # Add FK constraint if missing
    existing_fks = {fk["name"] for fk in insp.get_foreign_keys("line") if fk.get("name")}
    if "fk_line_subagency" not in existing_fks:
        op.create_foreign_key(
            "fk_line_subagency",
            "line",
            "subagency",
            ["subagency_id", "agency_name"],
            ["id", "agency_name"],
            ondelete="SET NULL"
        )


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    existing_fks = {fk["name"] for fk in insp.get_foreign_keys("line") if fk.get("name")}
    if "fk_line_subagency" in existing_fks:
        op.drop_constraint("fk_line_subagency", "line", type_="foreignkey")

    existing_cols = {col["name"] for col in insp.get_columns("line")}
    if "subagency_id" in existing_cols:
        op.drop_column("line", "subagency_id")
