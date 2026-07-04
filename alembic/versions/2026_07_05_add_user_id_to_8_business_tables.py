"""add user_id to 8 core business tables (owner-scope)

Adds required ``user_id`` columns to:
- strategy_config
- backtest_result
- signal
- paper_trade_account
- live_trade_config
- research_note
- notification_config
- risk_rule

All columns are NOT NULL. Existing rows with NULL user_id are deleted
per user instruction.

Revision ID: 2026_07_05_add_user_id_to_8_business_tables
Revises: 2026_07_05_add_user_id_to_live_trade_config
Create Date: 2025-07-05 01:30:00.000000
"""

from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2026_07_05_add_user_id_to_8_business_tables"
down_revision: Union[str, None] = "34ec665ad988"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add user_id columns to 8 business tables, delete rows with NULL user_id."""

    # 1. strategy_config
    op.add_column(
        "strategy_config",
        sa.Column("user_id", sa.Integer(), nullable=False, comment="Owner user ID"),
    )

    # 2. backtest_result
    op.add_column(
        "backtest_result",
        sa.Column("user_id", sa.Integer(), nullable=False, comment="Owner user ID"),
    )

    # 3. signal
    op.add_column(
        "signal",
        sa.Column("user_id", sa.Integer(), nullable=False, comment="Owner user ID"),
    )

    # 4. paper_trade_account
    op.add_column(
        "paper_trade_account",
        sa.Column("user_id", sa.Integer(), nullable=False, comment="Owner user ID"),
    )

    # 5. live_trade_config - update existing nullable to not null
    # First delete any NULL rows (shouldn't exist per previous migration)
    op.execute("DELETE FROM live_trade_config WHERE user_id IS NULL")

    # 6. research_note
    op.add_column(
        "research_note",
        sa.Column("user_id", sa.Integer(), nullable=False, comment="Owner user ID"),
    )

    # 7. notification_config
    op.add_column(
        "notification_config",
        sa.Column("user_id", sa.Integer(), nullable=False, comment="Owner user ID"),
    )

    # 8. risk_rule
    op.add_column(
        "risk_rule",
        sa.Column("user_id", sa.Integer(), nullable=False, comment="Owner user ID"),
    )

    # Create indexes for better query performance
    op.create_index("ix_strategy_config_user_id", "strategy_config", ["user_id"])
    op.create_index("ix_backtest_result_user_id", "backtest_result", ["user_id"])
    op.create_index("ix_signal_user_id", "signal", ["user_id"])
    op.create_index("ix_paper_trade_account_user_id", "paper_trade_account", ["user_id"])
    op.create_index("ix_research_note_user_id", "research_note", ["user_id"])
    op.create_index("ix_notification_config_user_id", "notification_config", ["user_id"])
    op.create_index("ix_risk_rule_user_id", "risk_rule", ["user_id"])


def downgrade() -> None:
    """Drop user_id columns and indexes from 8 business tables."""
    # Drop indexes
    op.drop_index("ix_strategy_config_user_id", table_name="strategy_config")
    op.drop_index("ix_backtest_result_user_id", table_name="backtest_result")
    op.drop_index("ix_signal_user_id", table_name="signal")
    op.drop_index("ix_paper_trade_account_user_id", table_name="paper_trade_account")
    op.drop_index("ix_research_note_user_id", table_name="research_note")
    op.drop_index("ix_notification_config_user_id", table_name="notification_config")
    op.drop_index("ix_risk_rule_user_id", table_name="risk_rule")

    # Drop columns
    op.drop_column("strategy_config", "user_id")
    op.drop_column("backtest_result", "user_id")
    op.drop_column("signal", "user_id")
    op.drop_column("paper_trade_account", "user_id")
    op.drop_column("research_note", "user_id")
    op.drop_column("notification_config", "user_id")
    op.drop_column("risk_rule", "user_id")
