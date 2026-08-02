"""add daily_digest table

每日夜间 AI 综合研报（2026-08-03，Daily Digest B1）：新建
``daily_digest`` 表，承载每天 06:30 (Asia/Shanghai) 生成的全局
综合研报（6 章节 markdown 全文 + 摘要 + 逐章节状态 + 聚合层
元数据）。``report_date`` 全局唯一，同日重生成走 upsert；
``report_metadata_id`` 弱关联 report_metadata 伴随行
（ondelete SET NULL），供通知通道沿用 report_id 语义。

Revision ID: b7d9f1h3j5l7
Revises: x5y7z9a1b3c5
Create Date: 2026-08-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7d9f1h3j5l7"
down_revision: Union[str, Sequence[str], None] = "x5y7z9a1b3c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "daily_digest",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="ID"),
        sa.Column(
            "report_date",
            sa.Date(),
            nullable=False,
            comment="报告日期（窗口结束日，Asia/Shanghai 当日 06:30 收口）",
        ),
        sa.Column(
            "report_metadata_id",
            sa.Integer(),
            nullable=True,
            comment="伴随的 report_metadata 行 ID（通知通道 report_id 语义）",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            comment="pending / running / success / partial / failed",
        ),
        sa.Column("title", sa.String(length=200), nullable=True, comment="报告标题"),
        sa.Column(
            "summary_md",
            sa.Text(),
            nullable=True,
            comment="AI 摘要（≤200 字，Dashboard 摘要卡 / 推送首条用）",
        ),
        sa.Column("content_md", sa.Text(), nullable=True, comment="6 章节 markdown 全文"),
        sa.Column(
            "sections_json",
            sa.JSON(),
            nullable=True,
            comment="逐章节状态 [{key,title,status,chars}]，failed 节含占位段说明",
        ),
        sa.Column(
            "data_snapshot_json",
            sa.JSON(),
            nullable=True,
            comment="聚合层元数据：窗口起止、各数据包行数、degraded 列表",
        ),
        sa.Column(
            "llm_model",
            sa.String(length=50),
            nullable=True,
            comment="生成所用 LLM 模型名（provider.model）",
        ),
        sa.Column("error_msg", sa.Text(), nullable=True, comment="整体失败时的错误信息"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True, comment="生成开始时间"),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True, comment="生成完成时间"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
            comment="创建时间",
        ),
        sa.ForeignKeyConstraint(
            ["report_metadata_id"], ["report_metadata.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    # 模型定义是 Column(unique=True, index=True)——SQLAlchemy 将其合并为
    # 一个唯一索引（而非约束+索引各一份），迁移同样只建唯一索引以对齐。
    op.create_index(
        "ix_daily_digest_report_date", "daily_digest", ["report_date"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_daily_digest_report_date", table_name="daily_digest")
    op.drop_table("daily_digest")
