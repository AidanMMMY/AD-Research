"""add user_article_state table

学习中心 P1（2026-08-02）：新建用户文章状态表
``user_article_state``（(user_id, article_id) 复合 PK，
bookmarked_at / read_at 可空时间戳），承载学习中心知识库的
"稍后读"（收藏切换）与"已读"两种文章级用户状态。

状态不写进 ``news_article``（全局共享爬虫表），单独建表；
两列均 CASCADE 外键，用户注销 / 文章清理时状态行随之删除。

Revision ID: x5y7z9a1b3c5
Revises: w4x6y8z0a2b4
Create Date: 2026-08-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "x5y7z9a1b3c5"
down_revision: Union[str, Sequence[str], None] = "w4x6y8z0a2b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_article_state",
        sa.Column(
            "user_id",
            sa.Integer(),
            nullable=False,
            comment="用户 ID（users.id），复合主键之一",
        ),
        sa.Column(
            "article_id",
            sa.Integer(),
            nullable=False,
            comment="文章 ID（news_article.id），复合主键之一",
        ),
        sa.Column(
            "bookmarked_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="收藏时间；NULL=未收藏（取消收藏置 NULL 不删行，保留已读状态）",
        ),
        sa.Column(
            "read_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="首次标记已读时间；NULL=未读（重复标记不改写原时间戳）",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            comment="状态行创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            comment="状态行最近更新时间",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["article_id"], ["news_article.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "article_id"),
    )
    # 收藏列表按 user_id 过滤 + bookmarked_at 排序；
    # 复合主键 (user_id, article_id) 本身已覆盖 feed LEFT JOIN 的
    # (article_id, user_id) 等值查找吗？——主键索引前导列是 user_id，
    # feed join 是 article_id 等值，需补一个 article_id 前导索引。
    op.create_index(
        "ix_user_article_state_article_id",
        "user_article_state",
        ["article_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_article_state_article_id", table_name="user_article_state"
    )
    op.drop_table("user_article_state")
