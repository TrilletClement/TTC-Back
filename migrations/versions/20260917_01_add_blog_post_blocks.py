"""Add blocks + accent_color to blog_post (éditeur d'articles par blocs).

Revision ID: 20260917_01
Revises: 20260916_01
Create Date: 2026-09-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260917_01"
down_revision: Union[str, None] = "20260916_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # `blocks` est le document source de l'éditeur visuel ; `content` reste le
    # HTML rendu (servi tel quel par la page publique, indexé, utilisé par les
    # extraits). NULL = article écrit avant l'éditeur, ou en HTML libre —
    # l'éditeur s'ouvre alors en mode HTML au lieu d'écraser le contenu.
    op.add_column(
        "blog_post",
        sa.Column("blocks", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "blog_post",
        sa.Column("accent_color", sa.String(length=7), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("blog_post", "accent_color")
    op.drop_column("blog_post", "blocks")
