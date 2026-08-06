"""add performance indexes

性能审计（2026-08-06）：为热路径查询补齐缺失索引，消除顺序扫描 /
filesort：

* ``research_note(instrument_code, created_at)`` — 按标的拉取研报
* ``sentiment_data(instrument_code, ingested_at)`` + ``(published_at)``
  — 情绪聚合查询（此前整表无索引）
* ``ai_chat_session(user_id)`` + ``ai_chat_message(session_id, created_at)``
  — 聊天历史加载
* ``signal(created_at DESC)`` + ``(etf_code, trade_date)`` — 信号看板
* ``etf_score(template_id, trade_date, rank_overall)`` — 评分榜 / 报告排序
* ``notification_log(config_id, created_at)`` — 通知 SSE 轮询

Revision ID: e8f0a2c4d6e8
Revises: c4d6e8f0a2b4
Create Date: 2026-08-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8f0a2c4d6e8"
down_revision: Union[str, Sequence[str], None] = "c4d6e8f0a2b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_research_note_instrument_created",
        "research_note",
        ["instrument_code", "created_at"],
    )
    op.create_index(
        "ix_sentiment_data_instrument_ingested",
        "sentiment_data",
        ["instrument_code", "ingested_at"],
    )
    op.create_index(
        "ix_sentiment_data_published_at",
        "sentiment_data",
        ["published_at"],
    )
    op.create_index(
        "ix_ai_chat_session_user_id",
        "ai_chat_session",
        ["user_id"],
    )
    op.create_index(
        "ix_ai_chat_message_session_created",
        "ai_chat_message",
        ["session_id", "created_at"],
    )
    op.create_index(
        "ix_signal_created_at_desc",
        "signal",
        [sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_signal_etf_code_trade_date",
        "signal",
        ["etf_code", "trade_date"],
    )
    op.create_index(
        "idx_etf_score_template_date_rank",
        "etf_score",
        ["template_id", "trade_date", "rank_overall"],
    )
    op.create_index(
        "ix_notification_log_config_created",
        "notification_log",
        ["config_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notification_log_config_created", table_name="notification_log")
    op.drop_index("idx_etf_score_template_date_rank", table_name="etf_score")
    op.drop_index("ix_signal_etf_code_trade_date", table_name="signal")
    op.drop_index("ix_signal_created_at_desc", table_name="signal")
    op.drop_index("ix_ai_chat_message_session_created", table_name="ai_chat_message")
    op.drop_index("ix_ai_chat_session_user_id", table_name="ai_chat_session")
    op.drop_index("ix_sentiment_data_published_at", table_name="sentiment_data")
    op.drop_index(
        "ix_sentiment_data_instrument_ingested",
        table_name="sentiment_data",
    )
    op.drop_index(
        "ix_research_note_instrument_created",
        table_name="research_note",
    )
