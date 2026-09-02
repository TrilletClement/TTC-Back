"""Add cover_image_url to blog_post

Revision ID: 20260902_01
Revises: 20260828_02
Create Date: 2026-09-02 22:10:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "20260902_01"
down_revision = "20260828_02"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "blog_post",
        sa.Column("cover_image_url", sa.String(length=500), nullable=True),
    )


def downgrade():
    op.drop_column("blog_post", "cover_image_url")
