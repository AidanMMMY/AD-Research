"""add news_article.duplicate_of column

修复模型-迁移漂移（2026-08-08 功能审计）：``app/models/news.py`` 定义了
``duplicate_of``（近似重复文章指向旧文，ondelete SET NULL，自引用 FK），
但 alembic env.py 从未加载该文件（``app/models/news`` 包遮蔽），导致
该列从未生成迁移 → 生产/本地 ``news_article`` 查询
``SELECT ... duplicate_of`` 直接 UndefinedColumn 500，新闻列表/详情/
learning feed 全部不可用。

配套修复：``alembic/env.py`` 经 ``_model_loader.load_news_models()``
加载 news 模型，此后 autogenerate 能正确对比该表。

Revision ID: f0b2d4e6f8a0
Revises: e8f0a2c4d6e8
Create Date: 2026-08-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f0b2d4e6f8a0"
down_revision: Union[str, Sequence[str], None] = "e8f0a2c4d6e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "news_article",
        sa.Column(
            "duplicate_of",
            sa.Integer(),
            nullable=True,
            comment="Points to the older article this row is a near-duplicate of",
        ),
    )
    # 自引用 FK（近似去重）：删除被指向文章时置 NULL。
    op.create_foreign_key(
        "news_article_duplicate_of_fkey",
        "news_article",
        "news_article",
        ["duplicate_of"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_news_article_duplicate_of", "news_article", ["duplicate_of"])


def downgrade() -> None:
    op.drop_index("ix_news_article_duplicate_of", table_name="news_article")
    op.drop_constraint("news_article_duplicate_of_fkey", "news_article", type_="foreignkey")
    op.drop_column("news_article", "duplicate_of")
