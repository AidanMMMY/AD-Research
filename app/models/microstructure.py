"""A-share micro-structure data models.

Stores four classes of A-share micro-structure signals sourced from
akshare:

* ``LhbRecord`` - 龙虎榜 (Top-list) - intraday top buyers / sellers
  disclosure for stocks with extreme moves or trading activity.
* ``HsgtFlow`` - 沪深港通 (Shanghai-Shenzhen-Hong Kong Stock Connect)
  daily summary flows.
* ``MarginBalance`` - 融资融券 (margin trading) underlying balance
  per stock per exchange per trade date.
* ``RestrictedRelease`` - 限售解禁 (restricted-share release) future
  unlock schedule for individual stocks.

Each table has an idempotency-friendly unique constraint so the daily
refresh is safe to re-run.
"""

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)

from app.core.database import Base


class LhbRecord(Base):
    """One 龙虎榜 (Top-list) disclosure for a stock on a trade date.

    The same stock may appear on the top-list multiple times on the
    same day with different ``reason`` values (e.g. ``日涨幅偏离值
    达7%`` *and* ``日换手率达20%``), hence the unique key is
    ``(trade_date, ts_code, reason)`` rather than just the pair.
    """

    __tablename__ = "lhb_records"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")

    trade_date = Column(Date, nullable=False, index=True, comment="交易日期")
    ts_code = Column(String(20), nullable=False, index=True, comment="证券代码 (含后缀)")
    name = Column(String(64), nullable=False, comment="证券简称")

    close = Column(Numeric(12, 4), comment="收盘价 (元)")
    pct_change = Column(Numeric(10, 4), comment="涨跌幅 (%)")
    turnover_rate = Column(Numeric(10, 4), comment="换手率 (%)")
    amount = Column(Numeric(20, 4), comment="成交额 (元)")

    lhb_buy_amount = Column(Numeric(20, 4), comment="龙虎榜买入额 (元)")
    lhb_sell_amount = Column(Numeric(20, 4), comment="龙虎榜卖出额 (元)")
    lhb_net_amount = Column(Numeric(20, 4), comment="龙虎榜净额 (元, 买-卖)")

    total_buy = Column(Numeric(20, 4), comment="总买入额 (元)")
    total_sell = Column(Numeric(20, 4), comment="总卖出额 (元)")
    total_net = Column(Numeric(20, 4), comment="总净额 (元)")
    net_buy_amt = Column(Numeric(20, 4), comment="买方净额 (元)")

    buy_seat_count = Column(Integer, comment="买方营业部个数")
    sell_seat_count = Column(Integer, comment="卖方营业部个数")

    reason = Column(String(256), nullable=False, comment="上榜原因")
    source = Column(
        String(32),
        nullable=False,
        server_default="akshare",
        comment="数据来源",
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="入库时间",
    )

    __table_args__ = (
        UniqueConstraint(
            "trade_date", "ts_code", "reason",
            name="uq_lhb_records_trade_date_ts_code_reason",
        ),
        Index("ix_lhb_records_trade_date_amount", "trade_date", "lhb_net_amount"),
    )


class HsgtFlow(Base):
    """Daily 沪深港通 (HSGT) capital-flow summary.

    ``type`` is one of:
    * ``北向`` — aggregate Northbound (沪股通 + 深股通)
    * ``沪股通`` — Shanghai-HK Connect (Northbound, SH leg)
    * ``深股通`` — Shenzhen-HK Connect (Northbound, SZ leg)
    * ``南向`` — aggregate Southbound (HK to A)
    """

    __tablename__ = "hsgt_flows"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")

    trade_date = Column(Date, nullable=False, index=True, comment="交易日期")
    type = Column(
        String(16), nullable=False, index=True,
        comment="资金流向类型: 北向/沪股通/深股通/南向",
    )

    buy_amount = Column(Numeric(20, 4), comment="买入成交额 (元)")
    sell_amount = Column(Numeric(20, 4), comment="卖出成交额 (元)")
    net_amount = Column(Numeric(20, 4), comment="净流入 (元)")
    balance = Column(Numeric(20, 4), comment="当日余额 (元)")

    source = Column(
        String(32),
        nullable=False,
        server_default="akshare",
        comment="数据来源",
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="入库时间",
    )

    __table_args__ = (
        UniqueConstraint(
            "trade_date", "type",
            name="uq_hsgt_flows_trade_date_type",
        ),
    )


class MarginBalance(Base):
    """融资融券 (margin trading) balance per stock per trade date.

    ``exchange`` distinguishes the SSE and SZSE legs (SSE / SZSE) — the
    two exchanges publish margin data through separate endpoints with
    different schemas.  All monetary fields are in 元 (CNY).
    """

    __tablename__ = "margin_balances"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")

    trade_date = Column(Date, nullable=False, index=True, comment="交易日期")
    ts_code = Column(String(20), nullable=False, index=True, comment="证券代码 (含后缀)")
    name = Column(String(64), nullable=False, comment="证券简称")

    financing_balance = Column(Numeric(20, 4), comment="融资余额 (元)")
    financing_buy = Column(Numeric(20, 4), comment="融资买入额 (元)")
    securities_balance = Column(Numeric(20, 4), comment="融券余额 (元)")
    securities_sell = Column(Numeric(20, 4), comment="融券卖出量 (股)")

    exchange = Column(
        String(8), nullable=False, comment="交易所: SSE / SZSE",
    )
    source = Column(
        String(32),
        nullable=False,
        server_default="akshare",
        comment="数据来源",
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="入库时间",
    )

    __table_args__ = (
        UniqueConstraint(
            "trade_date", "ts_code",
            name="uq_margin_balances_trade_date_ts_code",
        ),
        Index("ix_margin_balances_exchange_trade_date", "exchange", "trade_date"),
    )


class RestrictedRelease(Base):
    """限售解禁 (restricted-share release) schedule for a single stock.

    The same stock may have multiple unlock events (different
    ``restricted_type`` / 限售类型) on the same date — e.g. 定向增发
    (private placement) *and* 股权激励 (equity incentive), hence the
    unique key is ``(ts_code, restricted_date, restricted_type)``.
    """

    __tablename__ = "restricted_releases"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")

    ts_code = Column(String(20), nullable=False, index=True, comment="证券代码 (含后缀)")
    name = Column(String(64), nullable=False, comment="证券简称")
    restricted_date = Column(Date, nullable=False, index=True, comment="解禁日期")

    restricted_type = Column(
        String(64), nullable=False, server_default="",
        comment="限售类型: 定向增发/股权激励/首发原股东/...",
    )
    restricted_number = Column(Numeric(20, 4), comment="解禁数量 (股)")
    restricted_amount = Column(Numeric(20, 4), comment="解禁市值 (元)")
    lift_ratio = Column(Numeric(10, 4), comment="占总股本比例 (%)")

    source = Column(
        String(32),
        nullable=False,
        server_default="akshare",
        comment="数据来源",
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="入库时间",
    )

    __table_args__ = (
        UniqueConstraint(
            "ts_code", "restricted_date", "restricted_type",
            name="uq_restricted_releases_ts_code_date_type",
        ),
    )
