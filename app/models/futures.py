"""Futures-related ORM models.

Stores Chinese-domestic futures contract metadata and daily bars
across SHFE, DCE, CZCE, CFFEX, INE and GFEX exchanges.

Distinct from ETF/Instrument models because futures:
  - Roll over to a new "main" contract every 1-3 months
  - Have settlement price and open interest as first-class fields
  - Use a leading "main contract" code (e.g. CU0) that doesn't match
    any specific delivery month
"""

from sqlalchemy import (
    DECIMAL,
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)

from app.core.database import Base


# Exchanges
EX_SHFE = "SHFE"  # 上期所 - Shanghai Futures Exchange
EX_DCE = "DCE"    # 大商所 - Dalian Commodity Exchange
EX_CZCE = "CZCE"  # 郑商所 - Zhengzhou Commodity Exchange
EX_CFFEX = "CFFEX"  # 中金所 - China Financial Futures Exchange
EX_INE = "INE"    # 上海能源中心 - Shanghai International Energy Exchange
EX_GFEX = "GFEX"  # 广期所 - Guangzhou Futures Exchange

EXCHANGE_LABELS = {
    EX_SHFE: "上期所",
    EX_DCE: "大商所",
    EX_CZCE: "郑商所",
    EX_CFFEX: "中金所",
    EX_INE: "上海能源",
    EX_GFEX: "广期所",
}

# Product categories
PROD_METAL = "金属"
PROD_ENERGY = "能源化工"
PROD_AGRI = "农产品"
PROD_FINANCIAL = "金融期货"

PRODUCT_LABELS = {
    PROD_METAL: "金属",
    PROD_ENERGY: "能源化工",
    PROD_AGRI: "农产品",
    PROD_FINANCIAL: "金融期货",
}


class FuturesContract(Base):
    """A futures main contract (continuous contract) per product.

    The ``code`` is the sina/main symbol such as ``CU0`` (上期所沪铜主力),
    ``M0`` (大商所豆粕主力), ``IF0`` (中金所股指主力).
    The ``underlying_instrument`` column records the actual delivery-month
    contract that this continuous contract currently rolls to, e.g.
    ``CU2606``.
    """

    __tablename__ = "futures_contracts"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    code = Column(String(20), unique=True, index=True, nullable=False, comment="Main contract code, e.g. CU0/M0/IF0")
    name = Column(String(200), nullable=False, comment="Display name, e.g. 沪铜主力")
    exchange = Column(String(10), index=True, nullable=False, comment="Exchange code: SHFE/DCE/CZCE/CFFEX/INE/GFEX")
    product = Column(String(20), index=True, nullable=False, comment="Category: 金属/能源化工/农产品/金融期货")
    list_date = Column(Date, comment="Contract listing date")
    delist_date = Column(Date, comment="Contract delist date (informational)")
    contract_size = Column(DECIMAL(18, 4), comment="Contract multiplier (e.g. 5吨/手)")
    price_unit = Column(String(20), comment="Price unit (元/吨, 元/克, etc.)")
    quote_unit = Column(String(20), comment="Quote unit (元, 元/吨)")
    underlying_instrument = Column(String(20), comment="Current leading specific contract code, e.g. CU2606")
    is_main = Column(Boolean, default=True, index=True, nullable=False, comment="Is this a main continuous contract")
    last_seen_at = Column(DateTime(timezone=True), comment="Last time akshare listed this main contract")
    source = Column(String(50), default="akshare", comment="Data source")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="Creation time")
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        comment="Update time",
    )

    __table_args__ = (
        Index("idx_futures_contracts_ex_product", "exchange", "product"),
        Index("idx_futures_contracts_is_main", "is_main"),
    )


class FuturesDailyBar(Base):
    """Daily OHLCV bar for a futures main continuous contract.

    Includes futures-specific columns: settle, pre_settle, open_interest
    and turnover.
    """

    __tablename__ = "futures_daily_bars"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    code = Column(String(20), index=True, nullable=False, comment="Futures main contract code")
    trade_date = Column(Date, index=True, nullable=False, comment="Trade date")

    open = Column(DECIMAL(12, 4), comment="Open price")
    high = Column(DECIMAL(12, 4), comment="High price")
    low = Column(DECIMAL(12, 4), comment="Low price")
    close = Column(DECIMAL(12, 4), comment="Close price")

    settle = Column(DECIMAL(12, 4), comment="Settlement price (期货结算价)")
    pre_settle = Column(DECIMAL(12, 4), comment="Previous settlement price")
    volume = Column(BigInteger, comment="Volume (lots)")
    open_interest = Column(BigInteger, comment="Open interest (持仓量)")
    turnover = Column(DECIMAL(20, 4), comment="Turnover in CNY (成交额)")
    warehouse_receipts = Column(BigInteger, comment="Warehouse receipts (仓单) - best effort, may be None")

    source = Column(String(50), default="akshare", comment="Data source")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="Creation time")

    __table_args__ = (
        UniqueConstraint("code", "trade_date", name="uq_futures_daily_bar_code_date"),
        Index("idx_futures_daily_bar_code_date", "code", "trade_date"),
        Index("idx_futures_daily_bar_date", "trade_date"),
    )
