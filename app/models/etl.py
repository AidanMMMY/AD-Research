"""ETL and strategy-related ORM models.

Contains tables for data source configuration, ETL job logs,
strategy configuration, backtest results, and trading signals.
"""

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)

from app.core.database import Base


class DataSourceConfig(Base):
    """Data source configuration table."""

    __tablename__ = "data_source_config"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    source_name = Column(
        String(50),
        unique=True,
        nullable=False,
        comment="Source name",
    )
    provider_class = Column(
        String(200),
        nullable=False,
        comment="Provider class path",
    )
    api_key = Column(String(500), comment="API key")
    rate_limit = Column(Integer, default=10, comment="Rate limit (requests per second)")
    is_active = Column(Boolean, default=True, comment="Is active")
    config_json = Column(JSON, comment="Additional config as JSON")
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


class ETLLog(Base):
    """ETL job execution log table."""

    __tablename__ = "etl_log"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    job_name = Column(String(100), nullable=False, comment="Job name")
    source = Column(String(50), comment="Data source")
    status = Column(
        String(20),
        nullable=False,
        comment="Status: pending/running/success/failed",
    )
    start_time = Column(DateTime(timezone=True), comment="Start time")
    end_time = Column(DateTime(timezone=True), comment="End time")
    records_count = Column(Integer, comment="Number of records processed")
    error_msg = Column(Text, comment="Error message")
    extra_data = Column(JSON, comment="Additional metadata as JSON")
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Creation time",
    )

    __table_args__ = (
        Index("idx_etl_logs_job", "job_name"),
        Index("idx_etl_logs_status", "status"),
    )


class StrategyConfig(Base):
    """Strategy configuration table (reserved for Sub-project 4)."""

    __tablename__ = "strategy_config"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    user_id = Column(Integer, nullable=False, comment="Owner user ID")
    name = Column(String(100), nullable=False, comment="Strategy name")
    description = Column(Text, comment="Strategy description")
    strategy_type = Column(String(50), comment="Strategy type")
    params = Column(JSON, comment="Strategy parameters as JSON")
    is_active = Column(Boolean, default=True, comment="Is active")
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


class BacktestResult(Base):
    """Backtest result table (reserved for Sub-project 4)."""

    __tablename__ = "backtest_result"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    user_id = Column(Integer, nullable=False, comment="Owner user ID")
    strategy_id = Column(
        Integer,
        ForeignKey("strategy_config.id", ondelete="CASCADE"),
        nullable=False,
        comment="Strategy ID",
    )
    start_date = Column(Date, comment="Backtest start date")
    end_date = Column(Date, comment="Backtest end date")
    metrics = Column(JSON, comment="Performance metrics as JSON")
    trades = Column(JSON, comment="Trade list as JSON")
    config_snapshot = Column(JSON, comment="Strategy config snapshot as JSON")
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Creation time",
    )


class Signal(Base):
    """Trading signal table (reserved for Sub-project 4)."""

    __tablename__ = "signal"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    user_id = Column(
        Integer,
        nullable=True,
        comment="Owner user ID (NULL for system-generated signals)",
    )
    strategy_id = Column(
        Integer,
        ForeignKey("strategy_config.id", ondelete="CASCADE"),
        nullable=False,
        comment="Strategy ID",
    )
    etf_code = Column(
        String(20),
        ForeignKey("etf_info.code", ondelete="CASCADE"),
        nullable=False,
        comment="ETF code",
    )
    trade_date = Column(Date, nullable=False, comment="Trade date")
    signal_type = Column(
        String(10),
        nullable=False,
        comment="Signal type: BUY/SELL/HOLD",
    )
    strength = Column(Integer, comment="Signal strength")
    extra_data = Column(JSON, comment="Additional metadata as JSON")
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Creation time",
    )

    __table_args__ = (
        UniqueConstraint(
            "strategy_id", "etf_code", "trade_date",
            name="uq_signal_strategy_etf_date",
        ),
    )
