"""add data_api_access_log

Revision ID: ace37e584fa0
Revises: e6a8c0d2f4b6
Create Date: 2026-11-04 00:22:26.213960

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ace37e584fa0"
down_revision: str | Sequence[str] | None = "e6a8c0d2f4b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_api_access_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("path", sa.String(length=255), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("client_ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_api_access_log_created_at", "data_api_access_log", ["created_at"])
    op.create_index("ix_data_api_access_log_path", "data_api_access_log", ["path"])


def downgrade() -> None:
    op.drop_index("ix_data_api_access_log_path", table_name="data_api_access_log")
    op.drop_index("ix_data_api_access_log_created_at", table_name="data_api_access_log")
    op.drop_table("data_api_access_log")
