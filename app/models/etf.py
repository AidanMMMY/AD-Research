"""ETF-related ORM models.

Contains tables for ETF basic info, daily OHLCV bars, technical indicators,
and foreign exchange rates.
"""


from sqlalchemy import (
    DECIMAL,
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)

from app.core.database import Base


class ETFInfo(Base):
    """Unified instrument information table (ETFs, individual stocks & crypto).

    Stores basic information for ETFs, individual equities, and cryptocurrency
    trading pairs across multiple markets. The ``instrument_type`` column
    distinguishes ETFs from individual stocks and crypto assets.
    """

    __tablename__ = "etf_info"

    code = Column(String(20), primary_key=True, comment="Instrument code (e.g. 510050.SH, AAPL.US)")
    name = Column(String(200), nullable=False, comment="Instrument name")
    name_zh = Column(
        String(200),
        nullable=True,
        comment="Chinese name (primarily for US/HK/JP foreign listings)",
    )
    exchange = Column(String(10), comment="Exchange code (SH, SZ, NYSE, NASDAQ, etc.)")
    market = Column(String(20), comment="Market (A股, US, HK, JP)")
    category = Column(String(50), comment="Category")
    sub_category = Column(String(50), comment="Sub-category")
    manager = Column(String(100), comment="Fund manager")
    currency = Column(String(10), default="CNY", comment="Currency (CNY, USD, HKD, JPY)")
    is_qdii = Column(Boolean, default=False, comment="Is QDII")
    underlying_index = Column(String(200), comment="Underlying index name")
    fund_size = Column(DECIMAL(18, 4), comment="Fund size / market cap in base currency")
    inception_date = Column(Date, comment="Inception date / IPO date")
    list_date = Column(Date, comment="Listing / first trading date")
    delist_date = Column(Date, nullable=True, comment="Delisting date (null if still active)")
    status = Column(String(20), default="active", comment="Status (active, delisted, suspended)")

    # Extended columns for US stocks (Phase 1-2)
    instrument_type = Column(
        String(20), server_default="ETF", comment="Instrument type: ETF, STOCK or CRYPTO"
    )
    sector = Column(String(100), comment="GICS sector")
    industry = Column(String(100), comment="GICS industry")
    market_cap = Column(DECIMAL(18, 4), comment="Market capitalization (USD for US stocks)")
    country = Column(String(50), comment="Country of listing")

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Creation time",
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        comment="Update time",
    )

    __table_args__ = (
        Index("idx_etf_info_market", "market"),
        Index("idx_etf_info_category", "category"),
        Index("idx_etf_info_status", "status"),
        Index("idx_etf_info_instrument_type", "instrument_type"),
    )


class InstrumentDailyBar(Base):
    """ETF daily OHLCV bar data."""

    __tablename__ = "instrument_daily_bar"

    etf_code = Column(
        String(20),
        ForeignKey("etf_info.code", ondelete="CASCADE"),
        primary_key=True,
        comment="ETF code",
    )
    trade_date = Column(Date, primary_key=True, comment="Trade date")
    open = Column(DECIMAL(12, 4), comment="Open price")
    high = Column(DECIMAL(12, 4), comment="High price")
    low = Column(DECIMAL(12, 4), comment="Low price")
    close = Column(DECIMAL(12, 4), comment="Close price")
    volume = Column(BigInteger, comment="Volume")
    amount = Column(DECIMAL(18, 4), comment="Turnover amount")
    adj_factor = Column(
        DECIMAL(18, 8),
        default=1.0,
        nullable=False,
        comment="Adjustment factor: close * adj_factor = split/dividend adjusted close",
    )
    pre_close = Column(DECIMAL(12, 4), comment="Previous close")
    change_pct = Column(DECIMAL(8, 4), comment="Change percentage")
    turnover_rate = Column(DECIMAL(8, 4), comment="Turnover rate")
    shares_outstanding = Column(BigInteger, comment="Shares outstanding")
    nav = Column(DECIMAL(12, 4), comment="Net asset value")
    discount_rate = Column(DECIMAL(8, 4), comment="Discount rate")
    is_synthetic = Column(
        Boolean, default=False, nullable=False, comment="Whether this bar is synthetic/demo data"
    )
    created_at = Column(DateTime, server_default=func.now(), comment="Creation time")


class ETFCorporateAction(Base):
    """Corporate actions: splits, reverse splits, and dividends.

    Used to reconstruct adjustment factors and audit price changes.
    """

    __tablename__ = "etf_corporate_action"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    etf_code = Column(
        String(20),
        ForeignKey("etf_info.code", ondelete="CASCADE"),
        nullable=False,
        comment="Instrument code",
    )
    action_date = Column(Date, nullable=False, comment="Effective date of the action")
    action_type = Column(
        String(20),
        nullable=False,
        comment="Action type: split / reverse_split / dividend",
    )
    ratio = Column(
        DECIMAL(18, 8),
        nullable=False,
        comment="Split ratio or dividend adjustment factor",
    )
    source = Column(String(50), comment="Data source (yfinance, tiingo, manual)")
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Creation time",
    )

    __table_args__ = (
        UniqueConstraint(
            "etf_code",
            "action_date",
            "action_type",
            name="uq_corp_action_code_date_type",
        ),
        Index("idx_corp_action_code", "etf_code"),
        Index("idx_corp_action_date", "action_date"),
    )


class ETFHolding(Base):
    """ETF holding (constituent) — one row per (ETF, underlying security).

    Tracks the underlying securities that an ETF holds. The
    ``holdings_as_of_date`` column is the reporting-period date the
    holding snapshot refers to (usually a quarter or semi-annual
    disclosure). It is strictly nullable so historical rows written
    before this column was added keep their pre-migration NULL.
    Front-end renders surface a "holdings as of YYYY-MM-DD" hint
    from this column.

    NOTE: there was no pre-existing holdings table as of 2026-07-04.
    This is the first concrete table for ETF holdings — the migration
    only becomes meaningful once the upsert pipeline starts writing
    ``holdings_as_of_date``. See alembic revision ``01aeaa464fc3``.
    """

    __tablename__ = "etf_holding"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    etf_code = Column(
        String(20),
        ForeignKey("etf_info.code", ondelete="CASCADE"),
        nullable=False,
        comment="ETF / fund code",
    )
    holding_code = Column(
        String(20),
        nullable=False,
        comment="Underlying security code (e.g. 600519.SH, AAPL.US)",
    )
    holding_name = Column(String(200), comment="Underlying security display name")
    weight = Column(
        DECIMAL(10, 6),
        comment="Holding weight as a decimal fraction (0.05 = 5%)",
    )
    shares = Column(DECIMAL(18, 4), comment="Shares held")
    market_value = Column(DECIMAL(18, 4), comment="Market value in base currency")
    holdings_as_of_date = Column(
        Date,
        nullable=True,
        comment="Reporting-period date for this snapshot (e.g. quarterly disclosure)",
    )
    source = Column(String(50), comment="Data source (csindex, sse, manual)")
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Creation time",
    )

    __table_args__ = (
        UniqueConstraint(
            "etf_code",
            "holding_code",
            "holdings_as_of_date",
            name="uq_etf_holding_code_date",
        ),
        Index("idx_etf_holding_etf", "etf_code"),
        Index("idx_etf_holding_as_of", "holdings_as_of_date"),
    )


class ETFIndicator(Base):
    """ETF daily technical indicators."""

    __tablename__ = "etf_indicator"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    etf_code = Column(
        String(20),
        ForeignKey("etf_info.code", ondelete="CASCADE"),
        nullable=False,
        comment="ETF code",
    )
    trade_date = Column(Date, nullable=False, comment="Trade date")
    ma5 = Column(DECIMAL(12, 4), comment="MA5")
    ma10 = Column(DECIMAL(12, 4), comment="MA10")
    ma20 = Column(DECIMAL(12, 4), comment="MA20")
    ma60 = Column(DECIMAL(12, 4), comment="MA60")
    rsi14 = Column(DECIMAL(8, 4), comment="RSI14")
    macd_dif = Column(DECIMAL(12, 4), comment="MACD DIF")
    macd_dea = Column(DECIMAL(12, 4), comment="MACD DEA")
    macd_hist = Column(DECIMAL(12, 4), comment="MACD histogram")
    volatility_20d = Column(DECIMAL(8, 4), comment="20-day volatility")
    volatility_60d = Column(DECIMAL(8, 4), comment="60-day volatility")
    max_drawdown_1y = Column(DECIMAL(8, 4), comment="1-year max drawdown")
    sharpe_1y = Column(DECIMAL(8, 4), comment="1-year Sharpe ratio")
    return_1w = Column(DECIMAL(8, 4), comment="1-week return")
    return_1m = Column(DECIMAL(8, 4), comment="1-month return")
    return_3m = Column(DECIMAL(8, 4), comment="3-month return")
    return_6m = Column(DECIMAL(8, 4), comment="6-month return")
    return_1y = Column(DECIMAL(8, 4), comment="1-year return")
    amount = Column(DECIMAL(18, 4), comment="Turnover amount")
    atr14 = Column(DECIMAL(12, 4), comment="ATR14")
    bb_upper = Column(DECIMAL(12, 4), comment="Bollinger upper band")
    bb_lower = Column(DECIMAL(12, 4), comment="Bollinger lower band")
    created_at = Column(DateTime, server_default=func.now(), comment="Creation time")

    __table_args__ = (
        UniqueConstraint("etf_code", "trade_date", name="uq_indicator_code_date"),
        Index("idx_indicators_date", "trade_date"),
        Index("idx_indicators_code_date", "etf_code", "trade_date"),
    )


class FXRate(Base):
    """Foreign exchange rate table."""

    __tablename__ = "fx_rate"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    from_currency = Column(String(10), nullable=False, comment="From currency")
    to_currency = Column(String(10), nullable=False, comment="To currency")
    trade_date = Column(Date, nullable=False, comment="Trade date")
    rate = Column(DECIMAL(18, 8), nullable=False, comment="Exchange rate")
    source = Column(String(50), comment="Data source")

    __table_args__ = (
        UniqueConstraint(
            "from_currency",
            "to_currency",
            "trade_date",
            name="uq_fx_rate_currency_date",
        ),
        Index("idx_fx_rates_date", "trade_date"),
    )


# ===========================================================================
# A-Share Individual Stock Models
# ===========================================================================


class StockFundamental(Base):
    """A-share individual stock daily valuation & market data.

    Sources from Tushare daily_basic endpoint. One row per stock per trading day.
    """

    __tablename__ = "stock_fundamental"

    stock_code = Column(
        String(20),
        ForeignKey("etf_info.code", ondelete="CASCADE"),
        primary_key=True,
        comment="Stock code (e.g. 000001.SZ)",
    )
    trade_date = Column(Date, primary_key=True, comment="Trade date")

    # Valuation
    pe_ttm = Column(DECIMAL(12, 4), comment="PE (TTM)")
    pb = Column(DECIMAL(12, 4), comment="PB (latest)")
    total_mv = Column(DECIMAL(18, 4), comment="Total market cap (万元 CNY)")
    float_mv = Column(DECIMAL(18, 4), comment="Free float market cap (万元 CNY)")
    circ_mv = Column(DECIMAL(18, 4), comment="Circulating market cap (万元 CNY)")

    # Liquidity
    turnover_rate_f = Column(DECIMAL(8, 4), comment="Free float turnover rate (%)")
    volume_ratio = Column(DECIMAL(8, 4), comment="Volume ratio")

    # Shares (万股)
    total_share = Column(DECIMAL(18, 4), comment="Total shares (万股)")
    float_share = Column(DECIMAL(18, 4), comment="Free float shares (万股)")
    free_share = Column(DECIMAL(18, 4), comment="Unrestricted shares (万股)")

    # Period metadata (added 2026-07-04 to disambiguate PE/PB across
    # reporting periods). Strictly nullable — existing rows stay NULL.
    # ``period_type`` ∈ {'Q1','Q2','Q3','Annual','TTM'} identifies the
    # reporting window the valuation was sourced from; ``announce_date``
    # is the public release date for that snapshot.
    period_type = Column(
        String(10),
        nullable=True,
        comment="Reporting period: Q1|Q2|Q3|Annual|TTM (TTM = trailing twelve months)",
    )
    announce_date = Column(
        DateTime,
        nullable=True,
        comment="Public release date for this snapshot",
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Creation time",
    )

    __table_args__ = (
        UniqueConstraint(
            "stock_code", "trade_date", name="uq_stock_fundamental_code_date"
        ),
        Index("idx_stock_fundamental_date", "trade_date"),
        Index("idx_stock_fundamental_code_date", "stock_code", "trade_date"),
    )


class StockIncome(Base):
    """A-share individual stock quarterly income statements.

    Source: Tushare income_vip endpoint. One row per report period per stock.
    """

    __tablename__ = "stock_income"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    stock_code = Column(
        String(20),
        ForeignKey("etf_info.code", ondelete="CASCADE"),
        nullable=False,
        comment="Stock code",
    )
    end_date = Column(Date, nullable=False, comment="Report period end date")
    report_type = Column(String(20), default="Q4", comment="Report type (Q1/Q2/Q3/Q4)")
    ann_date = Column(Date, comment="Announcement date")

    # Revenue & Profit
    total_revenue = Column(DECIMAL(18, 4), comment="Total revenue (万元)")
    revenue_yoy = Column(DECIMAL(8, 4), comment="Revenue YoY growth (%)")
    operate_profit = Column(DECIMAL(18, 4), comment="Operating profit (万元)")
    total_profit = Column(DECIMAL(18, 4), comment="Total profit (万元)")
    n_income = Column(DECIMAL(18, 4), comment="Net income (万元)")
    n_income_yoy = Column(DECIMAL(8, 4), comment="Net income YoY growth (%)")
    basic_eps = Column(DECIMAL(12, 4), comment="Basic EPS (元)")

    # Margins & ROE
    grossprofit_margin = Column(DECIMAL(8, 4), comment="Gross profit margin (%)")
    netprofit_margin = Column(DECIMAL(8, 4), comment="Net profit margin (%)")
    roe = Column(DECIMAL(8, 4), comment="ROE (%)")
    roe_dt = Column(DECIMAL(8, 4), comment="Deducted ROE (%)")

    # Cash flow
    n_operate_cashflow = Column(DECIMAL(18, 4), comment="Operating cash flow (万元)")

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Creation time",
    )

    __table_args__ = (
        UniqueConstraint(
            "stock_code", "end_date", "report_type", name="uq_stock_income_code_period"
        ),
        Index("idx_stock_income_code", "stock_code"),
        Index("idx_stock_income_end_date", "end_date"),
    )


class StockBalanceSheet(Base):
    """A-share individual stock quarterly balance sheets.

    Source: Tushare balancesheet_vip endpoint. One row per report period per stock.
    """

    __tablename__ = "stock_balance_sheet"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    stock_code = Column(
        String(20),
        ForeignKey("etf_info.code", ondelete="CASCADE"),
        nullable=False,
        comment="Stock code",
    )
    end_date = Column(Date, nullable=False, comment="Report period end date")
    report_type = Column(String(20), default="Q4", comment="Report type (Q1/Q2/Q3/Q4)")
    ann_date = Column(Date, comment="Announcement date")

    # Balance Sheet Key Items (万元)
    total_assets = Column(DECIMAL(18, 4), comment="Total assets (万元)")
    total_liab = Column(DECIMAL(18, 4), comment="Total liabilities (万元)")
    total_hldr_eqy_exc_min_int = Column(
        DECIMAL(18, 4), comment="Shareholders' equity excl. minority interest (万元)"
    )
    total_cur_assets = Column(DECIMAL(18, 4), comment="Total current assets (万元)")
    total_cur_liab = Column(DECIMAL(18, 4), comment="Total current liabilities (万元)")

    # Ratios
    current_ratio = Column(DECIMAL(8, 4), comment="Current ratio")
    debt_to_assets = Column(DECIMAL(8, 4), comment="Debt to assets ratio (%)")

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Creation time",
    )

    __table_args__ = (
        UniqueConstraint(
            "stock_code", "end_date", "report_type",
            name="uq_stock_balance_sheet_code_period",
        ),
        Index("idx_stock_bs_code", "stock_code"),
        Index("idx_stock_bs_end_date", "end_date"),
    )
