"""Search-trend ORM model.

Stores daily search-index observations from public data sources
(akshare 百度热搜 / 雪球热搜 + optional pytrends Google Trends) for a
curated list of A-share-related keywords (indices, stocks, macro
topics).

Idempotency is enforced via the composite unique constraint
``(keyword, region, source, trade_date)`` so the daily ETL pipeline
can re-run safely and overwrite stale values.

Notes on data quality
---------------------
Both baidu and google search indices are approximate.  They are useful
for *relative* trends (what's spiking today vs. last week) but should
not be treated as exact population-level statistics.  All consumers
must surface the disclaimer "数据仅供参考，非精确值".
"""

from sqlalchemy import (
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


class SearchTrend(Base):
    """One search-index observation.

    Attributes:
        keyword: The text being searched (e.g. "上证指数", "宁德时代").
        region: The market the keyword belongs to — "CN" by default.
        source: "baidu" or "google".
        trade_date: Observation date (UTC midnight, no timezone).
        value: The index value reported by the upstream source.
            The unit is source-specific (百度 搜索指数 vs. google
            Trends relative score) so it is not directly comparable
            across sources.
        is_partial: True if the upstream reported that this is an
            incomplete day (e.g. fetched mid-day).
        proxy_quality: Coarse data-quality flag — "high" for paid /
            official, "low" for scraped heuristics.  Defaults to
            "high" because the data sources we use are reasonable.
        fetched_at: When this row was last upserted.
        created_at: Row creation timestamp (kept for audit).
    """

    __tablename__ = "search_trends"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")

    keyword = Column(
        String(120),
        nullable=False,
        index=True,
        comment="搜索关键词",
    )
    region = Column(
        String(16),
        nullable=False,
        server_default="CN",
        index=True,
        comment="市场/区域代码 (CN/US/GLOBAL)",
    )
    source = Column(
        String(16),
        nullable=False,
        index=True,
        comment="数据来源: baidu / google",
    )
    trade_date = Column(
        Date,
        nullable=False,
        index=True,
        comment="交易日 (UTC midnight)",
    )
    value = Column(
        BigInteger,
        nullable=False,
        comment="指数值（来源不同单位不同）",
    )
    is_partial = Column(
        Boolean,
        nullable=False,
        server_default="false",
        comment="是否当日不完整（午间抓取等）",
    )
    proxy_quality = Column(
        String(16),
        nullable=False,
        server_default="high",
        comment="数据质量: high/low",
    )
    category = Column(
        String(32),
        nullable=True,
        comment="分类: indices/stocks/macro (来自关键词配置)",
    )
    fetched_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="最后抓取时间",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="创建时间",
    )

    __table_args__ = (
        UniqueConstraint(
            "keyword", "region", "source", "trade_date",
            name="uq_search_trends_keyword_region_source_date",
        ),
        Index("ix_search_trends_source_date", "source", "trade_date"),
        Index("ix_search_trends_keyword_date", "keyword", "trade_date"),
        Index("ix_search_trends_region_source_date", "region", "source", "trade_date"),
    )