"""add news_source_meta table

学习中心（方案 B MVP，2026-08-02）：新建资讯源内容性质元数据表
``news_source_meta``（source PK, content_type, topic,
difficulty_default, display_group, note），承载"深度分析/科普教育"
源标签。知识 feed API 通过 ``news_article.source`` join 本表，
不改 news_article 结构、不回填历史数据。

迁移只建表——种子数据由 ``scripts/seed_news_source_meta.py``
（``seed_source_meta``，幂等）手动灌入，避免迁移与环境数据耦合。

Revision ID: w4x6y8z0a2b4
Revises: v3w5x7y9z1a3
Create Date: 2026-08-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "w4x6y8z0a2b4"
down_revision: Union[str, Sequence[str], None] = "v3w5x7y9z1a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "news_source_meta",
        sa.Column(
            "source",
            sa.String(length=200),
            nullable=False,
            comment="资讯源标识，与 news_article.source 对齐（wechat_/indie_/gind_ 等命名空间）",
        ),
        sa.Column(
            "content_type",
            sa.String(length=20),
            nullable=False,
            comment="deep=深度分析/研究 | edu=科普教育（快讯源不打标、不入库）",
        ),
        sa.Column(
            "topic",
            sa.String(length=40),
            nullable=True,
            comment="allocation|valuation|macro|industry|psychology|tools|research（兜底深度类）",
        ),
        sa.Column(
            "difficulty_default",
            sa.String(length=10),
            nullable=True,
            comment="beginner|advanced；NULL=混合/不确定（源级近似，不做逐篇难度）",
        ),
        sa.Column(
            "display_group",
            sa.String(length=60),
            nullable=True,
            comment="运营分组标签（如 公众号/中文播客/英文独立源），便于后台管理",
        ),
        sa.Column(
            "note",
            sa.String(length=200),
            nullable=True,
            comment="备注（通常为源的显示名，便于 SQL 维护时辨认）",
        ),
        sa.PrimaryKeyConstraint("source"),
    )
    op.create_index(
        "ix_news_source_meta_topic",
        "news_source_meta",
        ["topic"],
    )
    op.create_index(
        "ix_news_source_meta_content_type",
        "news_source_meta",
        ["content_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_news_source_meta_content_type", table_name="news_source_meta")
    op.drop_index("ix_news_source_meta_topic", table_name="news_source_meta")
    op.drop_table("news_source_meta")
