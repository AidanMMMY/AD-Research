"""全球速览指数日线 OHLCV 存储模型.

为全球速览页（Global Markets）28 个宏观代码的详情页提供 K 线数据：

* yfinance 覆盖的国际指数 / 外汇 / 商品（^GSPC、EUR=X、CL=F 等）
* akshare 覆盖的 A 股指数（sh000001 / sz399001 / sh000300）

与 ``macro_indicator`` 的关系：``macro_indicator`` 只存每日收盘价
（value 单列），速览页磁贴与折线仍走它；本表额外存开高低收量，
专供详情页蜡烛图使用。两条写入路径完全独立，互不影响。

复合主键 (code, trade_date, source) 保证幂等：同一来源同一交易日
重复抓取只更新不新增。
"""

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Float,
    Index,
    String,
    func,
)

from app.core.database import Base


class GlobalIndexDailyBar(Base):
    """一条全球指数日线 OHLCV 记录.

    ``code`` 与 ``macro_indicator.code`` 使用同一套内部编码
    （如 ``global_sp500`` / ``usd_eur`` / ``global_shcomp``），
    但没有外键约束 —— 本表可以先于 macro_indicator 回填数据，
    详情页读取时再按 code 关联元数据。
    """

    __tablename__ = "global_index_daily_bar"

    # 内部代码（与 macro_indicator.code 一致），如 global_sp500
    code = Column(String(80), primary_key=True, comment="Indicator code")

    # 交易日
    trade_date = Column(Date, primary_key=True, comment="Trade date")

    # 数据来源：yfinance / akshare
    source = Column(
        String(20),
        primary_key=True,
        server_default="yfinance",
        comment="Data source",
    )

    # 开盘价（部分数据源/部分交易日可能缺失，如 FX 周末缺口）
    open = Column(Float, nullable=True, comment="Open price")
    high = Column(Float, nullable=True, comment="High price")
    low = Column(Float, nullable=True, comment="Low price")

    # 收盘价（详情页 latest/stats 的基准，必须存在）
    close = Column(Float, nullable=False, comment="Close price")

    # 成交量（FX 现货等无成交量，置 NULL）
    volume = Column(BigInteger, nullable=True, comment="Volume")

    fetched_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="When this row was last upserted",
    )

    __table_args__ = (
        Index("ix_global_index_daily_bar_code_date", "code", "trade_date"),
    )
