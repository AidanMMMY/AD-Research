"""add_crypto_trading_tables

Revision ID: 7d05c7c0d4f0
Revises: f6a7b8c9d0e1
Create Date: 2026-06-28 04:40:11.945634
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d05c7c0d4f0'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create paper & live trading tables (Phase 2+3)."""
    # ── Paper trade account ──
    op.create_table('paper_trade_account',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('initial_balance', sa.DECIMAL(precision=18, scale=4), nullable=False),
        sa.Column('cash', sa.DECIMAL(precision=18, scale=4), nullable=False),
        sa.Column('currency', sa.String(length=10), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )

    # ── Paper trade order ──
    op.create_table('paper_trade_order',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('paper_trade_account.id', ondelete='CASCADE'), nullable=False),
        sa.Column('instrument_code', sa.String(length=20), nullable=False),
        sa.Column('order_type', sa.String(length=10), nullable=False),
        sa.Column('price', sa.DECIMAL(precision=18, scale=8)),
        sa.Column('quantity', sa.DECIMAL(precision=18, scale=8), nullable=False),
        sa.Column('filled_quantity', sa.DECIMAL(precision=18, scale=8)),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('reject_reason', sa.String(length=500)),
        sa.Column('signal_id', sa.Integer(), sa.ForeignKey('signal.id', ondelete='SET NULL')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('filled_at', sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_pto_account_status', 'paper_trade_order', ['account_id', 'status'])
    op.create_index('ix_pto_instrument', 'paper_trade_order', ['instrument_code', 'created_at'])
    op.create_index(op.f('ix_paper_trade_order_account_id'), 'paper_trade_order', ['account_id'])
    op.create_index(op.f('ix_paper_trade_order_instrument_code'), 'paper_trade_order', ['instrument_code'])

    # ── Paper trade position ──
    op.create_table('paper_trade_position',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('account_id', sa.Integer(), sa.ForeignKey('paper_trade_account.id', ondelete='CASCADE'), nullable=False),
        sa.Column('instrument_code', sa.String(length=20), nullable=False),
        sa.Column('quantity', sa.DECIMAL(precision=18, scale=8), nullable=False),
        sa.Column('avg_cost', sa.DECIMAL(precision=18, scale=8), nullable=False),
        sa.Column('market_value', sa.DECIMAL(precision=18, scale=4)),
        sa.Column('unrealized_pnl', sa.DECIMAL(precision=18, scale=4)),
        sa.Column('realized_pnl', sa.DECIMAL(precision=18, scale=4)),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('account_id', 'instrument_code', name='uq_ptp_account_code')
    )
    op.create_index(op.f('ix_paper_trade_position_account_id'), 'paper_trade_position', ['account_id'])

    # ── Live trade config ──
    op.create_table('live_trade_config',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('api_key_encrypted', sa.String(length=512)),
        sa.Column('api_secret_encrypted', sa.String(length=512)),
        sa.Column('is_testnet', sa.Boolean(), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False),
        sa.Column('max_order_value', sa.DECIMAL(precision=18, scale=4)),
        sa.Column('max_daily_loss', sa.DECIMAL(precision=18, scale=4)),
        sa.Column('max_daily_orders', sa.Integer()),
        sa.Column('allowed_symbols', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )

    # ── Live trade order ──
    op.create_table('live_trade_order',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('config_id', sa.Integer(), sa.ForeignKey('live_trade_config.id', ondelete='CASCADE'), nullable=False),
        sa.Column('order_id_from_exchange', sa.String(length=100)),
        sa.Column('instrument_code', sa.String(length=20), nullable=False),
        sa.Column('side', sa.String(length=10), nullable=False),
        sa.Column('order_type', sa.String(length=20), nullable=False),
        sa.Column('price', sa.DECIMAL(precision=18, scale=8)),
        sa.Column('quantity', sa.DECIMAL(precision=18, scale=8), nullable=False),
        sa.Column('filled_quantity', sa.DECIMAL(precision=18, scale=8)),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('reject_reason', sa.String(length=500)),
        sa.Column('signal_id', sa.Integer(), sa.ForeignKey('signal.id', ondelete='SET NULL')),
        sa.Column('raw_response', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_lto_config_status', 'live_trade_order', ['config_id', 'status'])
    op.create_index('ix_lto_instrument_time', 'live_trade_order', ['instrument_code', 'created_at'])
    op.create_index(op.f('ix_live_trade_order_config_id'), 'live_trade_order', ['config_id'])
    op.create_index(op.f('ix_live_trade_order_instrument_code'), 'live_trade_order', ['instrument_code'])

    # ── Live trade position ──
    op.create_table('live_trade_position',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('config_id', sa.Integer(), sa.ForeignKey('live_trade_config.id', ondelete='CASCADE'), nullable=False),
        sa.Column('instrument_code', sa.String(length=20), nullable=False),
        sa.Column('quantity', sa.DECIMAL(precision=18, scale=8), nullable=False),
        sa.Column('avg_cost', sa.DECIMAL(precision=18, scale=8), nullable=False),
        sa.Column('current_price', sa.DECIMAL(precision=18, scale=8)),
        sa.Column('market_value', sa.DECIMAL(precision=18, scale=4)),
        sa.Column('unrealized_pnl', sa.DECIMAL(precision=18, scale=4)),
        sa.Column('realized_pnl', sa.DECIMAL(precision=18, scale=4)),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('config_id', 'instrument_code', name='uq_ltp_config_code')
    )
    op.create_index(op.f('ix_live_trade_position_config_id'), 'live_trade_position', ['config_id'])

    # ── Risk rule ──
    op.create_table('risk_rule',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('rule_type', sa.String(length=50), nullable=False),
        sa.Column('param_key', sa.String(length=50), nullable=False),
        sa.Column('param_value', sa.String(length=100), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Drop paper & live trading tables."""
    op.drop_table('risk_rule')
    op.drop_index(op.f('ix_live_trade_position_config_id'), table_name='live_trade_position')
    op.drop_table('live_trade_position')
    op.drop_index('ix_lto_instrument_time', table_name='live_trade_order')
    op.drop_index('ix_lto_config_status', table_name='live_trade_order')
    op.drop_index(op.f('ix_live_trade_order_instrument_code'), table_name='live_trade_order')
    op.drop_index(op.f('ix_live_trade_order_config_id'), table_name='live_trade_order')
    op.drop_table('live_trade_order')
    op.drop_table('live_trade_config')
    op.drop_index(op.f('ix_paper_trade_position_account_id'), table_name='paper_trade_position')
    op.drop_table('paper_trade_position')
    op.drop_index('ix_pto_instrument', table_name='paper_trade_order')
    op.drop_index('ix_pto_account_status', table_name='paper_trade_order')
    op.drop_index(op.f('ix_paper_trade_order_instrument_code'), table_name='paper_trade_order')
    op.drop_index(op.f('ix_paper_trade_order_account_id'), table_name='paper_trade_order')
    op.drop_table('paper_trade_order')
    op.drop_table('paper_trade_account')
