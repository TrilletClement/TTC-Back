"""Add editor role and blog_post table

Revision ID: 20260210_01
Revises: 20260204_01
Create Date: 2026-02-10 23:55:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "20260210_01"
down_revision = "20260204_01" # On se base sur la migration Admin
branch_labels = None
depends_on = None

def upgrade():
    # 1. Ajouter le rôle Editor
    op.execute(
        "INSERT INTO role (name, description) "
        "SELECT 'editor', 'Can create and edit blog posts' "
        "WHERE NOT EXISTS (SELECT 1 FROM role WHERE name = 'editor')"
    )

    # 2. Créer la table blog_post
    op.create_table(
        "blog_post",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=False),
        sa.Column("published", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["author_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id")
    )
    op.create_index(op.f("ix_blog_post_slug"), "blog_post", ["slug"], unique=True)

def downgrade():
    op.drop_index(op.f("ix_blog_post_slug"), table_name="blog_post")
    op.drop_table("blog_post")
    op.execute("DELETE FROM role WHERE name = 'editor'")