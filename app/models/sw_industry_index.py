"""Model: sw_industry_index_return (Phase 3 sector rotation).

Per-industry official return series for the 31 申万2021 level-1 indices.
Source: AKShare ``index_hist_sw`` (one full-history fetch per industry).
Refreshed weekly by ``app.tasks.sw_industry.refresh_sw_industry_returns``.

The ``sector_rotation_service`` consults this table when
``classification="SW"`` to swap the equal-weight constituents average
for the official index return. Falls back to equal-weight when the
table has no row for the requested ``(sw_l1_code, trade_date)``.
"""

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Index,
    Numeric,
    PrimaryKeyConstraint,
    String,
    func,
)

from app.core.database import Base


class SWIndustryIndexReturn(Base):
    """申万一级行业指数每日回报 (Phase 3 sector rotation 数据源)."""

    __tablename__ = "sw_industry_index_return"

    sw_l1_code = Column(
        String(20),
        nullable=False,
        comment="申万一级行业代码 (e.g. 801080), pairs with etf_info.sw_l1_code",
    )
    trade_date = Column(Date, nullable=False, comment="指数交易日")
    close = Column(Numeric(18, 4), comment="指数当日收盘点位")
    return_1w = Column(Numeric(18, 6), comment="过去 1 周回报 (5 交易日)")
    return_1m = Column(Numeric(18, 6), comment="过去 1 月回报 (21 交易日)")
    return_3m = Column(Numeric(18, 6), comment="过去 3 月回报 (63 交易日)")
    return_6m = Column(Numeric(18, 6), comment="过去 6 月回报 (126 交易日)")
    return_1y = Column(Numeric(18, 6), comment="过去 1 年回报 (252 交易日)")
    source = Column(
        String(20),
        nullable=False,
        server_default="akshare",
        comment="数据来源标记 (akshare / tushare / fallback)",
    )
    fetched_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="最近一次写入时间",
    )

    __table_args__ = (
        PrimaryKeyConstraint("sw_l1_code", "trade_date", name="pk_sw_industry_index_return"),
        Index("ix_sw_industry_index_return_trade_date", "trade_date"),
        Index("ix_sw_industry_index_return_fetched_at", "fetched_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"<SWIndustryIndexReturn sw_l1_code={self.sw_l1_code!r} "
            f"trade_date={self.trade_date} close={self.close}>"
        )