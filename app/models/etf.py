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
    """ETF basic information table."""

    __tablename__ = "etf_info"

    code = Column(String(20), primary_key=True, comment="ETF code")
    name = Column(String(100), nullable=False, comment="ETF name")
    exchange = Column(String(10), comment="Exchange code")
    market = Column(String(20), comment="Market (e.g. SH, SZ)")
    category = Column(String(50), comment="Category")
    sub_category = Column(String(50), comment="Sub-category")
    manager = Column(String(100), comment="Fund manager")
    currency = Column(String(10), default="CNY", comment="Currency")
    is_qdii = Column(Boolean, default=False, comment="Is QDII")
    underlying_index = Column(String(200), comment="Underlying index name")
    fund_size = Column(DECIMAL(18, 4), comment="Fund size in CNY (AUM)")
    inception_date = Column(Date, comment="Inception date")
    status = Column(String(20), default="active", comment="Status")
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
    )


class ETFDailyBar(Base):
    """ETF daily OHLCV bar data."""

    __tablename__ = "etf_daily_bar"

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
