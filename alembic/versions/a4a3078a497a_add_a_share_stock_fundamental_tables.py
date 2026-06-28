"""add_a_share_stock_fundamental_tables

Revision ID: a4a3078a497a
Revises: e5f6a7b8c9d0
Create Date: 2026-06-28 04:25:32.779600

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4a3078a497a'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add A-share individual stock fundamental, income, and balance sheet tables."""
    op.create_table('stock_fundamental',
        sa.Column('stock_code', sa.String(length=20), nullable=False,
                  comment='Stock code (e.g. 000001.SZ)'),
        sa.Column('trade_date', sa.Date(), nullable=False, comment='Trade date'),
        sa.Column('pe_ttm', sa.DECIMAL(precision=12, scale=4), comment='PE (TTM)'),
        sa.Column('pb', sa.DECIMAL(precision=12, scale=4), comment='PB (latest)'),
        sa.Column('total_mv', sa.DECIMAL(precision=18, scale=4), comment='Total market cap (万元)'),
        sa.Column('float_mv', sa.DECIMAL(precision=18, scale=4), comment='Free float market cap (万元)'),
        sa.Column('circ_mv', sa.DECIMAL(precision=18, scale=4), comment='Circulating market cap (万元)'),
        sa.Column('turnover_rate_f', sa.DECIMAL(precision=8, scale=4), comment='Free float turnover rate (%)'),
        sa.Column('volume_ratio', sa.DECIMAL(precision=8, scale=4), comment='Volume ratio'),
        sa.Column('total_share', sa.DECIMAL(precision=18, scale=4), comment='Total shares (万股)'),
        sa.Column('float_share', sa.DECIMAL(precision=18, scale=4), comment='Free float shares (万股)'),
        sa.Column('free_share', sa.DECIMAL(precision=18, scale=4), comment='Unrestricted shares (万股)'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'),
                  comment='Creation time'),
        sa.ForeignKeyConstraint(['stock_code'], ['etf_info.code'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('stock_code', 'trade_date'),
        sa.UniqueConstraint('stock_code', 'trade_date', name='uq_stock_fundamental_code_date'),
    )
    op.create_index('idx_stock_fundamental_date', 'stock_fundamental', ['trade_date'])
    op.create_index('idx_stock_fundamental_code_date', 'stock_fundamental', ['stock_code', 'trade_date'])

    op.create_table('stock_income',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='ID'),
        sa.Column('stock_code', sa.String(length=20), nullable=False, comment='Stock code'),
        sa.Column('end_date', sa.Date(), nullable=False, comment='Report period end date'),
        sa.Column('report_type', sa.String(length=20), comment='Report type (Q1/Q2/Q3/Q4)'),
        sa.Column('ann_date', sa.Date(), comment='Announcement date'),
        sa.Column('total_revenue', sa.DECIMAL(precision=18, scale=4), comment='Total revenue (万元)'),
        sa.Column('revenue_yoy', sa.DECIMAL(precision=8, scale=4), comment='Revenue YoY growth (%)'),
        sa.Column('operate_profit', sa.DECIMAL(precision=18, scale=4), comment='Operating profit (万元)'),
        sa.Column('total_profit', sa.DECIMAL(precision=18, scale=4), comment='Total profit (万元)'),
        sa.Column('n_income', sa.DECIMAL(precision=18, scale=4), comment='Net income (万元)'),
        sa.Column('n_income_yoy', sa.DECIMAL(precision=8, scale=4), comment='Net income YoY growth (%)'),
        sa.Column('basic_eps', sa.DECIMAL(precision=12, scale=4), comment='Basic EPS (元)'),
        sa.Column('grossprofit_margin', sa.DECIMAL(precision=8, scale=4), comment='Gross profit margin (%)'),
        sa.Column('netprofit_margin', sa.DECIMAL(precision=8, scale=4), comment='Net profit margin (%)'),
        sa.Column('roe', sa.DECIMAL(precision=8, scale=4), comment='ROE (%)'),
        sa.Column('roe_dt', sa.DECIMAL(precision=8, scale=4), comment='Deducted ROE (%)'),
        sa.Column('n_operate_cashflow', sa.DECIMAL(precision=18, scale=4), comment='Operating cash flow (万元)'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'),
                  comment='Creation time'),
        sa.ForeignKeyConstraint(['stock_code'], ['etf_info.code'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stock_code', 'end_date', 'report_type', name='uq_stock_income_code_period'),
    )
    op.create_index('idx_stock_income_code', 'stock_income', ['stock_code'])
    op.create_index('idx_stock_income_end_date', 'stock_income', ['end_date'])

    op.create_table('stock_balance_sheet',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='ID'),
        sa.Column('stock_code', sa.String(length=20), nullable=False, comment='Stock code'),
        sa.Column('end_date', sa.Date(), nullable=False, comment='Report period end date'),
        sa.Column('report_type', sa.String(length=20), comment='Report type (Q1/Q2/Q3/Q4)'),
        sa.Column('ann_date', sa.Date(), comment='Announcement date'),
        sa.Column('total_assets', sa.DECIMAL(precision=18, scale=4), comment='Total assets (万元)'),
        sa.Column('total_liab', sa.DECIMAL(precision=18, scale=4), comment='Total liabilities (万元)'),
        sa.Column('total_hldr_eqy_exc_min_int', sa.DECIMAL(precision=18, scale=4),
                  comment="Shareholders' equity excl. minority interest (万元)"),
        sa.Column('total_cur_assets', sa.DECIMAL(precision=18, scale=4), comment='Total current assets (万元)'),
        sa.Column('total_cur_liab', sa.DECIMAL(precision=18, scale=4), comment='Total current liabilities (万元)'),
        sa.Column('current_ratio', sa.DECIMAL(precision=8, scale=4), comment='Current ratio'),
        sa.Column('debt_to_assets', sa.DECIMAL(precision=8, scale=4), comment='Debt to assets ratio (%)'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'),
                  comment='Creation time'),
        sa.ForeignKeyConstraint(['stock_code'], ['etf_info.code'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stock_code', 'end_date', 'report_type', name='uq_stock_balance_sheet_code_period'),
    )
    op.create_index('idx_stock_bs_code', 'stock_balance_sheet', ['stock_code'])
    op.create_index('idx_stock_bs_end_date', 'stock_balance_sheet', ['end_date'])


def downgrade() -> None:
    """Remove A-share individual stock tables."""
    op.drop_index('idx_stock_bs_end_date', table_name='stock_balance_sheet')
    op.drop_index('idx_stock_bs_code', table_name='stock_balance_sheet')
    op.drop_table('stock_balance_sheet')
    op.drop_index('idx_stock_income_end_date', table_name='stock_income')
    op.drop_index('idx_stock_income_code', table_name='stock_income')
    op.drop_table('stock_income')
    op.drop_index('idx_stock_fundamental_date', table_name='stock_fundamental')
    op.drop_index('idx_stock_fundamental_code_date', table_name='stock_fundamental')
    op.drop_table('stock_fundamental')
