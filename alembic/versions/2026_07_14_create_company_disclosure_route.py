"""create company_disclosure_route table

Revision ID: 2026_07_14_create_company_disclosure_route
Revises: h8i9j0k1l2m3
Create Date: 2026-07-14

Adds the ``company_disclosure_route`` table that stores per-ticker
exchange / cninfo / IR URLs plus last-verification metadata.  It is the
fallback source for ``CninfoReportService.download_with_fallback``
when cninfo's static.cninfo.com.cn CDN is unreachable: rows here let
the fallback provider rebuild candidate PDF URLs from SSE / SZSE / BSE
listing pages.

There was no pre-existing table when this migration was authored, so
``upgrade`` performs a full ``create_table``; ``downgrade`` drops it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "2026_07_14_create_company_disclosure_route"
down_revision = "h8i9j0k1l2m3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_disclosure_route",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False, comment="A 股代码（纯数字，如 600519）"),
        sa.Column("name", sa.String(length=200), nullable=False, comment="公司简称"),
        sa.Column(
            "exchange_code",
            sa.String(length=10),
            nullable=False,
            comment="交易所代码: SSE / SZSE / BSE",
        ),
        sa.Column(
            "sse_disclosure_url",
            sa.Text(),
            nullable=True,
            comment="上交所公告列表页 URL（仅 SSE 公司）",
        ),
        sa.Column(
            "szse_disclosure_url",
            sa.Text(),
            nullable=True,
            comment="深交所公告列表页 URL（仅 SZSE 公司）",
        ),
        sa.Column(
            "cninfo_disclosure_url",
            sa.Text(),
            nullable=True,
            comment="巨潮资讯网公告页 URL（大部分公司可用）",
        ),
        sa.Column(
            "ir_website_url",
            sa.Text(),
            nullable=True,
            comment="公司官网投资者关系主页 URL（agent 发现）",
        ),
        sa.Column(
            "ir_discovery_method",
            sa.String(length=50),
            nullable=True,
            comment="IR URL 发现方式: web_search | manual | ai_inferred",
        ),
        sa.Column(
            "last_verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最近一次成功验证时间",
        ),
        sa.Column(
            "verification_status",
            sa.String(length=20),
            server_default=sa.text("'pending'"),
            nullable=False,
            comment="验证状态: pending / verified / failed / stale",
        ),
        sa.Column(
            "verification_notes",
            sa.Text(),
            nullable=True,
            comment="验证备注（失败原因等）",
        ),
        sa.Column(
            "market_cap_rank",
            sa.Integer(),
            nullable=True,
            comment="市值排名（NULL = 非 A 股或未排行）",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_company_disclosure_route"),
        sa.UniqueConstraint("code", name="uq_company_disclosure_route_code"),
    )
    op.create_index(
        "idx_cdr_exchange", "company_disclosure_route", ["exchange_code"]
    )
    op.create_index(
        "idx_cdr_status", "company_disclosure_route", ["verification_status"]
    )
    op.create_index(
        "idx_cdr_rank", "company_disclosure_route", ["market_cap_rank"]
    )


def downgrade() -> None:
    op.drop_index("idx_cdr_rank", table_name="company_disclosure_route")
    op.drop_index("idx_cdr_status", table_name="company_disclosure_route")
    op.drop_index("idx_cdr_exchange", table_name="company_disclosure_route")
    op.drop_table("company_disclosure_route")
