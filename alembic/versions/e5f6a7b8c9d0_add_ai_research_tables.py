"""add AI research tables

Revision ID: e5f6a7b8c9d0
Revises: d3f4e5a6b7c8
Create Date: 2025-06-25

Create research_note, sentiment_data, ai_chat_session, and ai_chat_message
tables for the AI "Vibe Trading" research layer.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d3f4e5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # research_note
    op.create_table(
        "research_note",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("instrument_code", sa.String(20), sa.ForeignKey("etf_info.code", ondelete="CASCADE"), nullable=False),
        sa.Column("note_type", sa.String(50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.String(500)),
        sa.Column("sentiment", sa.String(20)),
        sa.Column("confidence", sa.Integer()),
        sa.Column("source_data", sa.JSON()),
        sa.Column("generated_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    # sentiment_data
    op.create_table(
        "sentiment_data",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("instrument_code", sa.String(20), sa.ForeignKey("etf_info.code", ondelete="CASCADE"), nullable=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("content", sa.Text()),
        sa.Column("url", sa.String(1000)),
        sa.Column("sentiment_score", sa.DECIMAL(5, 4)),
        sa.Column("sentiment_label", sa.String(20)),
        sa.Column("confidence", sa.DECIMAL(5, 4)),
        sa.Column("published_at", sa.DateTime()),
        sa.Column("ingested_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    # ai_chat_session
    op.create_table(
        "ai_chat_session",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )

    # ai_chat_message
    op.create_table(
        "ai_chat_message",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("ai_chat_session.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("ai_chat_message")
    op.drop_table("ai_chat_session")
    op.drop_table("sentiment_data")
    op.drop_table("research_note")
