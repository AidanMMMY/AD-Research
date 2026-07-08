"""add etf_holding_unavailable table and etf_holding_stats view

Adds a structurally-unavailable blacklist for the ETF top-10 holdings
ETL plus a coverage / stats view that the monitoring dashboard
(``GET /api/v1/etf-holdings/{stats,coverage,unavailable}``) is built on.

The blacklist captures 33 currency and physical-gold/SGE-gold ETFs whose
holdings are not exposed via the Tushare / Akshare ``fund_portfolio``
endpoints.  Including them in the ETL run either wastes a request slot
or — worse — records empty / zero-weight rows that drag the coverage
metric down.  Marking them as structurally unavailable lets the ETL
skip them and lets the coverage KPI use ``count_active - count_black``
as the denominator so a 100% pass rate is achievable.

The stats view aggregates ``etf_holding`` by ``snapshot_date`` so the
monitoring endpoints can answer "how many ETFs / rows / sources did we
land for each reporting period" with a single round-trip and without
shipping per-row data over the wire.

Revision ID: b5e2c8f4a1d3
Revises: a3f8e1b2c4d5
Create Date: 2026-07-08
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "b5e2c8f4a1d3"
down_revision = "a3f8e1b2c4d5"
branch_labels = None
depends_on = None


# 33 structurally-unavailable A-share ETFs (verified against the
# production ``etf_info`` snapshot on 2026-07-08).
#
# Categories:
#   - currency  (19)  — sub_category='货币基金' or category='货币型';
#                      do not publish top-10 holdings (only NAV).
#   - physical gold / SGE gold / 金ETF (14) — hold physical bullion
#                      allocated at a single depository, no top-10 list.
#
# Excluded from the list (verified to publish top-10 holdings or to be
# already covered):
#   * 黄金股ETF (gold-mining equity ETF) — holds listed gold stocks,
#     fund_portfolio returns the top-10 equity holdings normally.
#   * 标普油气ETF (S&P oil & gas ETF) — index-tracking, fund_portfolio
#     returns the index constituent top-10.
#   * 豆粕/能源化工/大宗商品ETF — commodity futures-backed but the
#     provider still publishes a single-line "all in CU contract" row.
#   * 511010.SH 国债ETF — only A-share bond ETF; fund_portfolio returns
#     the bond-ladder detail, not the format we need.
_UNAVAILABLE_ETFS: list[tuple[str, str, str]] = [
    # ── Currency (19) ──
    ("511620.SH", "货币型", "货币型 ETF — 不公布 top-10 holdings（仅披露 NAV）"),
    ("511650.SH", "货币型", "货币型 ETF — 不公布 top-10 holdings（仅披露 NAV）"),
    ("511660.SH", "货币型", "货币型 ETF — 不公布 top-10 holdings（仅披露 NAV）"),
    ("511670.SH", "货币型", "货币型 ETF — 不公布 top-10 holdings（仅披露 NAV）"),
    ("511690.SH", "货币型", "货币型 ETF — 不公布 top-10 holdings（仅披露 NAV）"),
    ("511700.SH", "货币型", "货币型 ETF — 不公布 top-10 holdings（仅披露 NAV）"),
    ("511770.SH", "货币型", "货币型 ETF — 不公布 top-10 holdings（仅披露 NAV）"),
    ("511800.SH", "货币型", "货币型 ETF — 不公布 top-10 holdings（仅披露 NAV）"),
    ("511810.SH", "货币型", "货币型 ETF — 不公布 top-10 holdings（仅披露 NAV）"),
    ("511830.SH", "货币型", "货币型 ETF — 不公布 top-10 holdings（仅披露 NAV）"),
    ("511860.SH", "货币型", "货币型 ETF — 不公布 top-10 holdings（仅披露 NAV）"),
    ("511900.SH", "货币型", "货币型 ETF — 不公布 top-10 holdings（仅披露 NAV）"),
    ("511910.SH", "货币型", "货币型 ETF — 不公布 top-10 holdings（仅披露 NAV）"),
    ("511920.SH", "货币型", "货币型 ETF — 不公布 top-10 holdings（仅披露 NAV）"),
    ("511930.SH", "货币型", "货币型 ETF — 不公布 top-10 holdings（仅披露 NAV）"),
    ("511950.SH", "货币型", "货币型 ETF — 不公布 top-10 holdings（仅披露 NAV）"),
    ("511960.SH", "货币型", "货币型 ETF — 不公布 top-10 holdings（仅披露 NAV）"),
    ("511970.SH", "货币型", "货币型 ETF — 不公布 top-10 holdings（仅披露 NAV）"),
    ("511980.SH", "货币型", "货币型 ETF — 不公布 top-10 holdings（仅披露 NAV）"),
    # ── Physical gold / SGE gold (14) ──
    ("159812.SZ", "商品型", "实物黄金 ETF — 单一金库持仓，无 top-10 holdings 概念"),
    ("159830.SZ", "商品型", "金 ETF — 实物黄金，无 top-10 holdings"),
    ("159831.SZ", "商品型", "金 ETF — 实物黄金，无 top-10 holdings"),
    ("159834.SZ", "商品型", "金 ETF — 实物黄金，无 top-10 holdings"),
    ("159934.SZ", "商品型", "黄金 ETF — 实物黄金，无 top-10 holdings"),
    ("159937.SZ", "商品型", "黄金 ETF — 实物黄金，无 top-10 holdings"),
    ("518600.SH", "商品型", "金 ETF — 实物黄金，无 top-10 holdings"),
    ("518660.SH", "商品型", "黄金 ETF — 实物黄金，无 top-10 holdings"),
    ("518680.SH", "商品型", "金 ETF — 实物黄金，无 top-10 holdings"),
    ("518800.SH", "商品型", "黄金 ETF — 实物黄金，无 top-10 holdings"),
    ("518850.SH", "商品型", "黄金 ETF — 实物黄金，无 top-10 holdings"),
    ("518860.SH", "商品型", "上海金 ETF — SGE 实物金，无 top-10 holdings"),
    ("518880.SH", "商品型", "黄金 ETF — 实物黄金，无 top-10 holdings"),
    ("518890.SH", "商品型", "上海金 ETF — SGE 实物金，无 top-10 holdings"),
]


def upgrade() -> None:
    """Create the blacklist table, seed it, and define the stats view."""
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 1. Blacklist table — one row per structurally-unavailable ETF.
    #    ``etf_code`` is the FK target but declared without an explicit
    #    ForeignKey() so this migration does not depend on the etf_info
    #    table being present in every test / shadow environment.
    op.create_table(
        "etf_holding_unavailable",
        sa.Column(
            "etf_code",
            sa.String(20),
            primary_key=True,
            comment="Instrument code marked as structurally-unavailable",
        ),
        sa.Column(
            "category",
            sa.String(50),
            nullable=False,
            comment="Unavailable category: 货币型 | 商品型 | 债券型 | 其他",
        ),
        sa.Column(
            "reason",
            sa.String(500),
            nullable=False,
            comment="Why this ETF was marked unavailable (Chinese explanation)",
        ),
        sa.Column(
            "marked_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="When the row was inserted into the blacklist",
        ),
        sa.Column(
            "marked_by",
            sa.String(50),
            nullable=True,
            comment="Who/what marked it (manual, etf_holdings_quarterly, etc.)",
        ),
    )
    op.create_index(
        op.f("idx_etf_holding_unavailable_category"),
        "etf_holding_unavailable",
        ["category"],
    )

    # 2. Seed the 33 known-unavailable ETFs.  ``INSERT ... ON CONFLICT
    #    DO NOTHING`` keeps the migration idempotent — re-running on a
    #    seeded database is a no-op.
    for code, category, reason in _UNAVAILABLE_ETFS:
        if is_postgres:
            op.execute(
                sa.text(
                    "INSERT INTO etf_holding_unavailable "
                    "(etf_code, category, reason, marked_by) "
                    "VALUES (:code, :cat, :reason, 'agent_research_2026_07_08') "
                    "ON CONFLICT (etf_code) DO NOTHING"
                ).bindparams(code=code, cat=category, reason=reason)
            )
        else:
            # SQLite / MySQL — use plain insert + ignore duplicate.
            op.execute(
                sa.text(
                    "INSERT OR IGNORE INTO etf_holding_unavailable "
                    "(etf_code, category, reason, marked_by) "
                    "VALUES (:code, :cat, :reason, 'agent_research_2026_07_08')"
                ).bindparams(code=code, cat=category, reason=reason)
            )

    # 3. Stats view — aggregated snapshot / source counters that the
    #    monitoring endpoints read from.  Created as a view (not a
    #    materialised view) so it always reflects the latest
    #    ``etf_holding`` rows; the underlying table is keyed on
    #    (etf_code, snapshot_date, holding_code) so the aggregation is
    #    cheap (a few hundred unique snapshot dates max).
    if is_postgres:
        op.execute(
            """
            CREATE OR REPLACE VIEW etf_holding_stats AS
            SELECT
                snapshot_date,
                COUNT(DISTINCT etf_code)            AS etf_count,
                COUNT(*)                            AS row_count,
                COUNT(DISTINCT source)              AS source_count,
                array_agg(DISTINCT source)          AS sources,
                MIN(created_at)                     AS first_ingested_at,
                MAX(created_at)                     AS last_ingested_at,
                (CURRENT_DATE - snapshot_date)      AS days_ago
            FROM etf_holding
            WHERE snapshot_date IS NOT NULL
            GROUP BY snapshot_date
            ORDER BY snapshot_date DESC
            """
        )
    else:
        # SQLite fallback — same shape, no array_agg.
        op.execute(
            """
            CREATE OR REPLACE VIEW etf_holding_stats AS
            SELECT
                snapshot_date,
                COUNT(DISTINCT etf_code)            AS etf_count,
                COUNT(*)                            AS row_count,
                COUNT(DISTINCT source)              AS source_count,
                GROUP_CONCAT(DISTINCT source)       AS sources,
                MIN(created_at)                     AS first_ingested_at,
                MAX(created_at)                     AS last_ingested_at,
                (CAST(strftime('%J', DATE('now')) AS INTEGER)
                 - CAST(strftime('%J', snapshot_date) AS INTEGER)) AS days_ago
            FROM etf_holding
            WHERE snapshot_date IS NOT NULL
            GROUP BY snapshot_date
            ORDER BY snapshot_date DESC
            """
        )


def downgrade() -> None:
    """Drop the stats view and the blacklist table.

    We drop the view first because PostgreSQL has no ``DROP VIEW IF
    NOT EXISTS``-style guard for the cross-dialect case; the SQL
    statement is guarded inside the conditional so the same downgrade
    works on SQLite / MySQL too.
    """
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("DROP VIEW IF EXISTS etf_holding_stats")
    else:
        op.execute("DROP VIEW IF EXISTS etf_holding_stats")

    op.drop_index(
        op.f("idx_etf_holding_unavailable_category"),
        table_name="etf_holding_unavailable",
    )
    op.drop_table("etf_holding_unavailable")
