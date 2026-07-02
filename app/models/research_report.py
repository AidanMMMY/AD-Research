"""Research report ORM model.

Stores A-share / US research reports ingested from Eastmoney (via akshare).
Each row represents one analyst research report. The unique constraint
``(ts_code, title, publish_date)`` keeps the table idempotent across
re-runs of the daily pipeline.

PDF links are constructed from akshare's ``infoCode`` field as
``https://pdf.dfcfw.com/pdf/H2_{infoCode}_1.pdf`` / ``H3_*`` patterns.
A free-form ``raw_payload`` JSON column preserves the original upstream
record for audit.
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)

from app.core.database import Base


class ResearchReport(Base):
    """An analyst research report for a single instrument.

    ``ts_code`` uses the project's canonical code format
    (e.g. ``600519.SH`` for A-share, ``AAPL.US`` for US).
    ``source`` records which provider produced the row, with
    ``eastmoney`` as the default (akshare's ``stock_research_report_em``).
    """

    __tablename__ = "research_reports"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    ts_code = Column(String(20), nullable=False, index=True, comment="Tushare/cn 证券代码")
    name = Column(String(64), nullable=False, comment="证券简称")
    title = Column(String(500), nullable=False, comment="研报标题")
    org_name = Column(String(128), nullable=False, index=True, comment="发布机构(券商)")
    industry = Column(String(64), index=True, comment="行业(中信/申万)")
    publish_date = Column(Date, nullable=False, index=True, comment="发布日期")
    rating = Column(String(32), comment="东财评级: 买入/增持/中性/减持/卖出")
    pdf_url = Column(String(1000), comment="PDF 链接")
    summary = Column(Text, comment="DeepSeek 生成摘要 (≤200 字)")
    key_points = Column(JSON, comment="DeepSeek 提取的核心要点 (JSON 数组)")
    target_price = Column(Numeric(12, 4), comment="目标价 (元)")
    current_price_at_publish = Column(Numeric(12, 4), comment="发布时收盘价 (元)")
    source = Column(
        String(32),
        nullable=False,
        server_default="eastmoney",
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
        UniqueConstraint(
            "ts_code",
            "title",
            "publish_date",
            name="uq_research_reports_ts_title_date",
        ),
        # Note: per-column ``index=True`` above already creates indexes on
        # ts_code, org_name, industry, publish_date. Do NOT re-declare them
        # here — duplicate Index() objects with the same name would clash
        # with the auto-generated ones during Base.metadata.create_all.
    )
