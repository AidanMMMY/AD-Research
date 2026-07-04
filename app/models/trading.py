"""Trading model – paper-trade and live-trade ORM classes.

Paper trading (phase 2) tables:
  paper_trade_account  – simulated account with a USDT balance
  paper_trade_order    – individual buy / sell orders
  paper_trade_position – aggregated holdings per instrument

Live trading (phase 3) tables:
  live_trade_config   – encrypted Binance API credentials + risk limits
  live_trade_order    – orders sent to the exchange
  live_trade_position – on-exchange holdings snapshot
  risk_rule           – configurable risk-control rules
"""

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    DECIMAL,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


# ---------------------------------------------------------------------------
# Phase 2 – Paper (simulated) trading
# ---------------------------------------------------------------------------


class PaperTradeAccount(Base):
    """Simulated trading account with a USDT balance."""

    __tablename__ = "paper_trade_account"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="Auto-increment account ID")
    user_id = Column(Integer, nullable=False, comment="Owner user ID")
    name = Column(String(100), nullable=False, comment="Human-readable account label")
    initial_balance = Column(DECIMAL(18, 4), nullable=False, default=10000, comment="Starting USDT balance")
    cash = Column(DECIMAL(18, 4), nullable=False, comment="Available USDT cash")
    currency = Column(String(10), nullable=False, default="USDT", comment="Quote currency")
    status = Column(String(20), nullable=False, default="active", comment="active | archived")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="Account creation time")
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        comment="Last modification time",
    )

    # Relationships
    positions = relationship("PaperTradePosition", back_populates="account", lazy="dynamic")
    orders = relationship("PaperTradeOrder", back_populates="account", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<PaperTradeAccount id={self.id} name={self.name!r} cash={self.cash}>"


class PaperTradeOrder(Base):
    """A single simulated order (BUY / SELL).

    Orders are executed immediately at the prevailing price when placed
    (market-order semantics for simplicity).
    """

    __tablename__ = "paper_trade_order"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="Auto-increment order ID")
    account_id = Column(
        Integer,
        ForeignKey("paper_trade_account.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owning paper-trade account",
    )
    instrument_code = Column(String(20), nullable=False, index=True, comment="Instrument code, e.g. BTC.US")
    order_type = Column(String(10), nullable=False, comment="BUY | SELL")
    price = Column(DECIMAL(18, 8), comment="Execution price per unit")
    quantity = Column(DECIMAL(18, 8), nullable=False, comment="Order quantity in base asset")
    filled_quantity = Column(DECIMAL(18, 8), default=0, comment="Quantity that was filled")
    status = Column(String(20), nullable=False, default="pending", comment="pending | filled | cancelled | rejected")
    reject_reason = Column(String(500), comment="Reason if status=rejected")
    signal_id = Column(
        Integer,
        ForeignKey("signal.id", ondelete="SET NULL"),
        nullable=True,
        comment="Signal that triggered this order (optional)",
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="Order creation time")
    filled_at = Column(DateTime(timezone=True), comment="Time the order was filled")

    # Relationships
    account = relationship("PaperTradeAccount", back_populates="orders")

    __table_args__ = (
        Index("ix_pto_account_status", "account_id", "status"),
        Index("ix_pto_instrument", "instrument_code", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<PaperTradeOrder id={self.id} {self.order_type} {self.instrument_code}"
            f" qty={self.quantity} status={self.status}>"
        )


class PaperTradePosition(Base):
    """Aggregated holding for one instrument within one account.

    Updated whenever an order fills.  One row per (account_id, instrument_code).
    """

    __tablename__ = "paper_trade_position"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="Auto-increment position ID")
    account_id = Column(
        Integer,
        ForeignKey("paper_trade_account.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owning paper-trade account",
    )
    instrument_code = Column(String(20), nullable=False, comment="Instrument code, e.g. BTC.US")
    quantity = Column(DECIMAL(18, 8), nullable=False, default=0, comment="Current position size")
    avg_cost = Column(DECIMAL(18, 8), nullable=False, default=0, comment="Volume-weighted average entry price")
    market_value = Column(DECIMAL(18, 4), comment="Last-marked market value in USDT")
    unrealized_pnl = Column(DECIMAL(18, 4), comment="Unrealised profit / loss")
    realized_pnl = Column(DECIMAL(18, 4), default=0, comment="Realised profit / loss from closed lots")
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        comment="Last mark-to-market time",
    )

    # Relationships
    account = relationship("PaperTradeAccount", back_populates="positions")

    __table_args__ = (
        UniqueConstraint("account_id", "instrument_code", name="uq_ptp_account_code"),
    )

    def __repr__(self) -> str:
        return (
            f"<PaperTradePosition acct={self.account_id} {self.instrument_code}"
            f" qty={self.quantity} avg={self.avg_cost}>"
        )


# ---------------------------------------------------------------------------
# Phase 3 – Live (on-exchange) trading
# ---------------------------------------------------------------------------


class LiveTradeConfig(Base):
    """Binance API credentials and risk-limit configuration for one account.

    Secrets are encrypted at rest with the application's notification_encryption_key
    (same Fernet key already used for webhook credentials).
    """

    __tablename__ = "live_trade_config"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="Auto-increment config ID")
    user_id = Column(Integer, nullable=False, comment="Owner user ID")
    name = Column(String(100), nullable=False, comment="Human-readable label, e.g. 'Main Spot'")
    api_key_encrypted = Column(String(512), comment="Fernet-encrypted Binance API key")
    api_secret_encrypted = Column(String(512), comment="Fernet-encrypted Binance API secret")
    is_testnet = Column(Boolean, nullable=False, default=True, comment="Use testnet.binance.vision endpoints")
    is_enabled = Column(Boolean, nullable=False, default=False, comment="Master switch for this config")
    max_order_value = Column(DECIMAL(18, 4), default=100, comment="Max USDT value per single order")
    max_daily_loss = Column(DECIMAL(18, 4), default=500, comment="Max daily realised loss before circuit-breaker")
    max_daily_orders = Column(Integer, default=20, comment="Max orders per calendar day")
    allowed_symbols = Column(Text, comment="JSON array of allowed instrument codes, empty = all")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="Config creation time")
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        comment="Last modification time",
    )

    def __repr__(self) -> str:
        return f"<LiveTradeConfig id={self.id} name={self.name!r} enabled={self.is_enabled}>"


class LiveTradeOrder(Base):
    """An order placed on the Binance exchange (or testnet)."""

    __tablename__ = "live_trade_order"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="Auto-increment local order ID")
    config_id = Column(
        Integer,
        ForeignKey("live_trade_config.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owning trade config",
    )
    order_id_from_exchange = Column(String(100), comment="Order ID returned by Binance")
    instrument_code = Column(String(20), nullable=False, index=True, comment="Instrument code, e.g. BTC.US")
    side = Column(String(10), nullable=False, comment="BUY | SELL")
    order_type = Column(String(20), nullable=False, default="LIMIT", comment="LIMIT | MARKET")
    price = Column(DECIMAL(18, 8), comment="Limit price (null for MARKET)")
    quantity = Column(DECIMAL(18, 8), nullable=False, comment="Base asset quantity")
    filled_quantity = Column(DECIMAL(18, 8), default=0, comment="Cumulative filled quantity")
    status = Column(String(20), nullable=False, default="pending", comment="pending | filled | partially_filled | cancelled | rejected")
    reject_reason = Column(String(500), comment="Reason if status=rejected")
    signal_id = Column(
        Integer,
        ForeignKey("signal.id", ondelete="SET NULL"),
        nullable=True,
        comment="Signal that triggered this order (optional)",
    )
    raw_response = Column(Text, comment="Raw JSON response from Binance for debugging")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="Order creation time")
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        comment="Last status update time",
    )

    __table_args__ = (
        Index("ix_lto_config_status", "config_id", "status"),
        Index("ix_lto_instrument_time", "instrument_code", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<LiveTradeOrder id={self.id} {self.side} {self.instrument_code} status={self.status}>"


class LiveTradePosition(Base):
    """Current on-exchange position snapshot for one instrument."""

    __tablename__ = "live_trade_position"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="Auto-increment position ID")
    config_id = Column(
        Integer,
        ForeignKey("live_trade_config.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owning trade config",
    )
    instrument_code = Column(String(20), nullable=False, comment="Instrument code, e.g. BTC.US")
    quantity = Column(DECIMAL(18, 8), nullable=False, default=0, comment="Current position size")
    avg_cost = Column(DECIMAL(18, 8), nullable=False, default=0, comment="Volume-weighted average entry price")
    current_price = Column(DECIMAL(18, 8), comment="Last known price")
    market_value = Column(DECIMAL(18, 4), comment="Current market value in USDT")
    unrealized_pnl = Column(DECIMAL(18, 4), comment="Unrealised PnL")
    realized_pnl = Column(DECIMAL(18, 4), default=0, comment="Realised PnL")
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        comment="Last sync time",
    )

    __table_args__ = (
        UniqueConstraint("config_id", "instrument_code", name="uq_ltp_config_code"),
    )

    def __repr__(self) -> str:
        return f"<LiveTradePosition cfg={self.config_id} {self.instrument_code} qty={self.quantity}>"


class RiskRule(Base):
    """A single configurable risk-control rule.

    Rules are evaluated in order; the first matching rule that REJECTs an order
    stops processing.  The `param_value` column holds type-specific thresholds
    as strings (e.g. "100.0", "true").
    """

    __tablename__ = "risk_rule"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="Auto-increment rule ID")
    user_id = Column(Integer, nullable=False, comment="Owner user ID")
    name = Column(String(100), nullable=False, comment="Human-readable rule name")
    rule_type = Column(String(50), nullable=False, comment="per_order | daily | market | duplicate")
    param_key = Column(String(50), nullable=False, comment="e.g. max_order_value, max_daily_loss")
    param_value = Column(String(100), nullable=False, comment="Threshold value as string")
    is_active = Column(Boolean, nullable=False, default=True, comment="Whether this rule is enforced")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="Rule creation time")

    def __repr__(self) -> str:
        return f"<RiskRule id={self.id} {self.rule_type}/{self.param_key} active={self.is_active}>"
