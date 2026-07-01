"""Listing / IPO event models.

Stores upcoming and recently-listed A-share IPO events, with fields
populated from Tushare's ``new_share`` endpoint (or the ``stock_basic``
fallback for free-tier users).
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
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


class ListingEvent(Base):
    """Upcoming or recently-listed A-share IPO event.

    Status semantics:
      * ``upcoming``   - both issue_date and list_date are in the future
      * ``subscribing``- issue_date <= today < list_date
      * ``listed``     - list_date <= today
      * ``unknown``    - both dates missing
    """

    __tablename__ = "listing_events"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    ts_code = Column(String(20), nullable=False, comment="Tushare 证券代码")
    sub_code = Column(String(20), comment="申购代码")
    name = Column(String(64), nullable=False, comment="证券简称")
    market = Column(String(8), nullable=False, comment="交易所后缀: SH/SZ/BJ")
    board = Column(String(16), nullable=False, comment="板块: 主板/创业板/科创板/北交所")
    industry = Column(String(64), comment="CSRC 行业")
    issue_date = Column(Date, comment="上网发行日期")
    list_date = Column(Date, comment="上市日期")
    issue_price = Column(Numeric(12, 4), comment="发行价 (元)")
    pe_ratio = Column(Numeric(10, 4), comment="发行市盈率")
    limit_amount = Column(Numeric(18, 4), comment="申购上限 (万元)")
    funds_raised = Column(Numeric(20, 4), comment="募集资金 (万元)")
    market_amount = Column(Numeric(20, 4), comment="发行后总股本 (万股)")
    sponsor = Column(String(128), comment="保荐机构")
    underwriter = Column(String(256), comment="承销商")
    status = Column(
        String(16),
        nullable=False,
        server_default="unknown",
        comment="状态: upcoming/subscribing/listed/unknown",
    )
    source = Column(
        String(32),
        nullable=False,
        server_default="tushare",
        comment="数据来源",
    )
    raw_payload = Column(JSON, comment="上游原始记录")
    fetched_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="抓取时间",
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="创建时间",
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间",
    )

    __table_args__ = (
        UniqueConstraint("ts_code", name="uq_listing_events_ts_code"),
        Index("ix_listing_events_list_date", "list_date"),
        Index("ix_listing_events_issue_date", "issue_date"),
        Index("ix_listing_events_status", "status"),
        Index("ix_listing_events_market_board", "market", "board"),
        Index("ix_listing_events_industry", "industry"),
    )
