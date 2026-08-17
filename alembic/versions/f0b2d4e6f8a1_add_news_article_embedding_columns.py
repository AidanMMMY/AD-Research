"""add news_article embedding columns

模型-迁移漂移续修（2026-08-08）：``news_article`` 的语义嵌入列
（``embedding`` / ``embedding_model`` / ``embedded_at``）同样因
``app/models/news.py`` 未纳入 alembic target_metadata 而从未迁移。
查询 ``SELECT ... embedding`` 在生产会 UndefinedColumn 500。

Revision ID: f0b2d4e6f8a1
Revises: f0b2d4e6f8a0
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f0b2d4e6f8a1"
down_revision: str | Sequence[str] | None = "f0b2d4e6f8a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("news_article", sa.Column("embedding", sa.JSON(), nullable=True))
    op.add_column(
        "news_article",
        sa.Column("embedding_model", sa.String(length=50), nullable=True),
    )
    op.add_column("news_article", sa.Column("embedded_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("news_article", "embedded_at")
    op.drop_column("news_article", "embedding_model")
    op.drop_column("news_article", "embedding")
