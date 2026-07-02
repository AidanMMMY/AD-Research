"""add cninfo_reports table

Revision ID: c1d2e3f4a5b6
Revises: a1b2c3d4e5f7
Create Date: 2026-07-02 11:00:00.000000

Adds the ``cninfo_reports`` table for A-share periodic reports fetched
from the public cninfo ``hisAnnouncement/query`` endpoint.  Mirrors
``app/models/cninfo_report.py``.  Unique constraint on
``announcement_id`` makes daily upserts idempotent.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "a1b2c3d4e5f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cninfo_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ts_code", sa.String(length=20), nullable=False, comment="Tushare 证券代码 (e.g. 600519.SH)"),
        sa.Column("stock_code", sa.String(length=20), nullable=False, comment="Stock 6-digit code (e.g. 600519)"),
        sa.Column("org_id", sa.String(length=32), nullable=True, comment="Cninfo orgId"),
        sa.Column("sec_code", sa.String(length=32), nullable=True, comment="Cninfo secCode"),
        sa.Column("announcement_id", sa.String(length=64), nullable=False, comment="Cninfo 公告 ID"),
        sa.Column("announcement_title", sa.String(length=512), nullable=False, comment="公告标题"),
        sa.Column("adjunct_url", sa.String(length=512), nullable=False, comment="PDF 下载链接"),
        sa.Column("file_path", sa.String(length=1024), nullable=True, comment="本地 PDF 存储路径"),
        sa.Column("file_size", sa.BigInteger(), nullable=True, comment="PDF 文件大小 (bytes)"),
        sa.Column("announcement_time", sa.DateTime(timezone=True), nullable=False, comment="公告发布时间"),
        sa.Column(
            "adjunct_type",
            sa.String(length=32),
            nullable=False,
            comment="附件类型: annual/semi/q1/q3/other",
        ),
        sa.Column(
            "is_periodic",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="是否定期报告",
        ),
        sa.Column("fiscal_year", sa.Integer(), nullable=True, comment="财年 (e.g. 2025)"),
        sa.Column(
            "fiscal_quarter",
            sa.Integer(),
            nullable=True,
            comment="财季: 1=Q1, 2=半年报, 3=Q3, 4=年报",
        ),
        sa.Column("extracted_text", sa.Text(), nullable=True, comment="PDF 提取出的文本 (截断)"),
        sa.Column(
            "extraction_status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
            comment="文本提取状态: pending/downloading/extracted/failed",
        ),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True, comment="文本提取完成时间"),
        sa.Column(
            "source",
            sa.String(length=32),
            nullable=False,
            server_default="cninfo",
            comment="数据来源",
        ),
        sa.Column("raw_payload", sa.Text(), nullable=True, comment="上游公告 JSON 字符串 (debug)"),
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
        sa.UniqueConstraint("announcement_id", name="uq_cninfo_reports_announcement_id"),
    )
    op.create_index("ix_cninfo_reports_ts_code", "cninfo_reports", ["ts_code"])
    op.create_index("ix_cninfo_reports_stock_code", "cninfo_reports", ["stock_code"])
    op.create_index("ix_cninfo_reports_announcement_time", "cninfo_reports", ["announcement_time"])
    op.create_index("ix_cninfo_reports_is_periodic", "cninfo_reports", ["is_periodic"])
    op.create_index(
        "ix_cninfo_reports_periodic_quarter",
        "cninfo_reports",
        ["fiscal_year", "fiscal_quarter", "adjunct_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_cninfo_reports_periodic_quarter", table_name="cninfo_reports")
    op.drop_index("ix_cninfo_reports_is_periodic", table_name="cninfo_reports")
    op.drop_index("ix_cninfo_reports_announcement_time", table_name="cninfo_reports")
    op.drop_index("ix_cninfo_reports_stock_code", table_name="cninfo_reports")
    op.drop_index("ix_cninfo_reports_ts_code", table_name="cninfo_reports")
    op.drop_table("cninfo_reports")