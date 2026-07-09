"""add 申万一级行业 (SW L1) columns to etf_info

Adds ``sw_l1`` (申万一级行业名称) and ``sw_l1_code`` (e.g. 801080) to
``etf_info`` so the sector-rotation service can bucket A-share instruments
by 申万 (Shenwan) level-1 industries in addition to GICS.

GICS remains the cross-market default; SW is A-share-only and is populated
by the ``backfill_a_share_sw`` script (CSRC→SW static map by default, or
Tushare ``index_classify`` + ``index_member`` when ``--from-tushare`` is
passed). Both columns are nullable because non-A-share instruments and
unmapped rows have no SW classification.

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-07-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'h8i9j0k1l2m3'
down_revision: Union[str, Sequence[str], None] = 'g7h8i9j0k1l2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add sw_l1 / sw_l1_code columns to etf_info."""
    op.add_column(
        'etf_info',
        sa.Column(
            'sw_l1',
            sa.String(length=100),
            nullable=True,
            comment='申万一级行业名称 (SW 2021 level-1, A-share only)',
        ),
    )
    op.add_column(
        'etf_info',
        sa.Column(
            'sw_l1_code',
            sa.String(length=20),
            nullable=True,
            comment='申万一级行业代码 (e.g. 801080), pairs with sw_l1',
        ),
    )


def downgrade() -> None:
    """Drop sw_l1 / sw_l1_code columns from etf_info."""
    op.drop_column('etf_info', 'sw_l1_code')
    op.drop_column('etf_info', 'sw_l1')
