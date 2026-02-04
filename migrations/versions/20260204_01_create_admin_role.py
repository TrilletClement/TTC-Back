"""Create admin role

Revision ID: 20260204_01
Revises: 20240909_12
Create Date: 2026-02-04 00:00:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260204_01"
down_revision = "20240909_12"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "INSERT INTO role (name, description) "
        "SELECT 'admin', 'Admin role' "
        "WHERE NOT EXISTS (SELECT 1 FROM role WHERE name = 'admin')"
    )


def downgrade():
    op.execute("DELETE FROM role WHERE name = 'admin'")
