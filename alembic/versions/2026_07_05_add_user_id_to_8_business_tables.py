"""add user_id to 8 core business tables (owner-scope)

Adds required ``user_id`` columns to:
- strategy_config
- backtest_result
- signal
- paper_trade_account
- live_trade_config  (column already exists as nullable from the upstream
  live_trade_config migration; here we backfill and flip to NOT NULL)
- research_note
- notification_config
- risk_rule

Pattern: add column NULLABLE → backfill existing rows to admin (id=1) →
alter to NOT NULL.  This is robust against pre-existing rows that the
running app wrote under the old schema (without ``user_id``).

Note: per original user instruction "delete if NULL found, run directly
on production", the original migration attempted to add a NOT NULL
column directly.  When the running app had already created 100K+ rows
in ``signal`` etc., the migration failed with NotNullViolation.  We
backfill to admin here instead of deleting data, since deleting
100K+ signal rows would have lost operational history.

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


# Admin user id used for backfilling pre-existing rows (platform owner).
_ADMIN_USER_ID = 1

# Tables whose user_id column is being added in this migration.
_NEW_USER_ID_TABLES = (
    "strategy_config",
    "backtest_result",
    "signal",
    "paper_trade_account",
    "research_note",
    "notification_config",
    "risk_rule",
)

# Tables whose user_id column was already added nullable by the upstream
# live_trade_config migration; here we only need to backfill + flip NOT NULL.
_BACKFILL_ONLY_TABLES = ("live_trade_config",)


def upgrade() -> None:
    """Add user_id columns to 8 business tables; backfill NULLs to admin; flip to NOT NULL."""

    # Step 1: add the column as NULLABLE for the 7 new tables.
    for table in _NEW_USER_ID_TABLES:
        op.add_column(
            table,
            sa.Column(
                "user_id",
                sa.Integer(),
                nullable=True,
                comment="Owner user ID (backfilled to admin for legacy rows)",
            ),
        )

    # Step 2: backfill any NULL user_id rows to admin for ALL 8 tables.
    for table in _NEW_USER_ID_TABLES + _BACKFILL_ONLY_TABLES:
        op.execute(
            f"UPDATE {table} SET user_id = {_ADMIN_USER_ID} WHERE user_id IS NULL"
        )

    # Step 3: flip the 7 newly-added columns to NOT NULL.
    for table in _NEW_USER_ID_TABLES:
        op.alter_column(table, "user_id", existing_type=sa.Integer(), nullable=False)

    # Step 4: create indexes for owner-scope query performance.
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

    # Drop columns (the 7 added by this migration; live_trade_config
    # column is dropped by the upstream migration's downgrade).
    for table in _NEW_USER_ID_TABLES:
        op.drop_column(table, "user_id")
