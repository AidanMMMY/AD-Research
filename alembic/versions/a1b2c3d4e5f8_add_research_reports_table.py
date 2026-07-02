"""add research_reports table

Revision ID: a1b2c3d4e5f8
Revises: a1b2c3d4e5f7
Create Date: 2026-07-02 14:00:00.000000

Adds the ``research_reports`` table for the Phase-4 Eastmoney analyst
report pipeline. Each row is one analyst report for a single
instrument.  The unique constraint on ``(ts_code, title, publish_date)``
keeps the daily upsert idempotent.

JSON columns (raw_payload / key_points) use plain ``JSON`` so this
migration is portable across SQLite + PostgreSQL.  Indexes on the
common filter dimensions keep the API list queries cheap.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f8"
down_revision: str | None = "a1b2c3d4e5f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "research_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="ID"),
        sa.Column("ts_code", sa.String(length=20), nullable=False, comment="Tushare/cn 证券代码"),
        sa.Column("name", sa.String(length=64), nullable=False, comment="证券简称"),
        sa.Column("title", sa.String(length=500), nullable=False, comment="研报标题"),
        sa.Column("org_name", sa.String(length=128), nullable=False, comment="发布机构(券商)"),
        sa.Column("industry", sa.String(length=64), nullable=True, comment="行业(中信/申万)"),
        sa.Column("publish_date", sa.Date(), nullable=False, comment="发布日期"),
        sa.Column("rating", sa.String(length=32), nullable=True, comment="东财评级: 买入/增持/中性/减持/卖出"),
        sa.Column("pdf_url", sa.String(length=1000), nullable=True, comment="PDF 链接"),
        sa.Column("summary", sa.Text(), nullable=True, comment="DeepSeek 生成摘要 (≤200 字)"),
        sa.Column("key_points", sa.JSON(), nullable=True, comment="DeepSeek 提取的核心要点 (JSON 数组)"),
        sa.Column("target_price", sa.Numeric(precision=12, scale=4), nullable=True, comment="目标价 (元)"),
        sa.Column(
            "current_price_at_publish",
            sa.Numeric(precision=12, scale=4),
            nullable=True,
            comment="发布时收盘价 (元)",
        ),
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'eastmoney'"),
            comment="数据来源",
        ),
        sa.Column("raw_payload", sa.JSON(), nullable=True, comment="上游原始记录"),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="抓取时间",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            comment="更新时间",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ts_code",
            "title",
            "publish_date",
            name="uq_research_reports_ts_code_title_date",
        ),
    )
    op.create_index("ix_research_reports_ts_code", "research_reports", ["ts_code"])
    op.create_index("ix_research_reports_org_name", "research_reports", ["org_name"])
    op.create_index("ix_research_reports_industry", "research_reports", ["industry"])
    op.create_index("ix_research_reports_publish_date", "research_reports", ["publish_date"])


def downgrade() -> None:
    op.drop_index("ix_research_reports_publish_date", table_name="research_reports")
    op.drop_index("ix_research_reports_industry", table_name="research_reports")
    op.drop_index("ix_research_reports_org_name", table_name="research_reports")
    op.drop_index("ix_research_reports_ts_code", table_name="research_reports")
    op.drop_table("research_reports")