"""免费资金流数据 ORM 模型（方案 C）。

对应 4 张表：

* ``IndividualFundFlow``  — 个股主力/超大/大/中/小单 资金流 (akshare)
* ``SectorFundFlow``      — 行业 / 概念 / 地域 板块资金流 (akshare)
* ``EtfFundFlow``         — ETF 折溢价 / 份额变化 / 推算净流入 (akshare)
* ``FlowSignal``          — 综合资金信号 (聚合多源)

每张表都有 ``(ts_code / sector_name, trade_date)`` 的唯一约束，保证
每日 ETL 重复跑安全 (upsert idempotent)。  所有货币字段单位均为
**元 (CNY)**，使用 ``Numeric(20, 4)`` 精度，与 micro-structure / scoring
保持一致。
"""

from __future__ import annotations

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
    text,
)

from app.core.database import Base


# ---------------------------------------------------------------------------
# 1. 个股资金流
# ---------------------------------------------------------------------------


class IndividualFundFlow(Base):
    """个股主力资金流 (按日)。

    数据源 ``ak.stock_individual_fund_flow_rank(indicator='今日')``，
    超大单 + 大单 = 主力 (机构口径)，中单 + 小单 = 散户。
    """

    __tablename__ = "individual_fund_flow"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")

    ts_code = Column(
        String(20), nullable=False, index=True, comment="证券代码 (含后缀, 如 600519.SH)"
    )
    trade_date = Column(Date, nullable=False, index=True, comment="交易日期")

    main_net_inflow = Column(Numeric(20, 4), comment="主力净流入净额 (元)")
    main_net_pct = Column(Numeric(8, 4), comment="主力净流入净占比 (%)")
    super_large_net = Column(Numeric(20, 4), comment="超大单净额 (元, ≥100万元)")
    super_large_pct = Column(Numeric(8, 4), comment="超大单净占比 (%)")
    large_net = Column(Numeric(20, 4), comment="大单净额 (元, 20-100万元)")
    large_pct = Column(Numeric(8, 4), comment="大单净占比 (%)")
    medium_net = Column(Numeric(20, 4), comment="中单净额 (元, 4-20万元)")
    medium_pct = Column(Numeric(8, 4), comment="中单净占比 (%)")
    small_net = Column(Numeric(20, 4), comment="小单净额 (元, <4万元)")
    small_pct = Column(Numeric(8, 4), comment="小单净占比 (%)")

    source = Column(
        String(20),
        nullable=False,
        server_default="akshare",
        comment="数据来源: akshare | eastmoney",
    )
    fetched_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="抓取时间",
    )

    __table_args__ = (
        UniqueConstraint(
            "ts_code", "trade_date",
            name="uq_individual_fund_flow_ts_code_date",
        ),
        Index(
            "ix_individual_fund_flow_main_net",
            "trade_date", "main_net_inflow",
        ),
    )


# ---------------------------------------------------------------------------
# 2. 板块资金流
# ---------------------------------------------------------------------------


class SectorFundFlow(Base):
    """板块资金流 (按日)。``sector_type`` ∈ {行业, 概念, 地域}。"""

    __tablename__ = "sector_fund_flow"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")

    sector_name = Column(String(100), nullable=False, index=True, comment="板块名称")
    sector_type = Column(
        String(20), nullable=False, index=True,
        comment="板块类型: 行业 / 概念 / 地域",
    )
    trade_date = Column(Date, nullable=False, index=True, comment="交易日期")

    main_net_inflow = Column(Numeric(20, 4), comment="板块主力净流入 (元)")
    main_net_pct = Column(Numeric(8, 4), comment="主力净流入净占比 (%)")
    super_large_net = Column(Numeric(20, 4), comment="超大单净额 (元)")
    large_net = Column(Numeric(20, 4), comment="大单净额 (元)")

    leading_stock = Column(
        String(100),
        comment="领涨股 (akshare 原始字段, 代码或名称)",
    )

    fetched_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="抓取时间",
    )

    __table_args__ = (
        UniqueConstraint(
            "sector_name", "sector_type", "trade_date",
            name="uq_sector_fund_flow_sector_type_date",
        ),
        Index(
            "ix_sector_fund_flow_main_net",
            "trade_date", "main_net_inflow",
        ),
    )


# ---------------------------------------------------------------------------
# 3. ETF 资金流
# ---------------------------------------------------------------------------


class EtfFundFlow(Base):
    """ETF 折溢价 / 份额变化 / 推算净流入 (按日)。

    ``inferred_net_inflow = shares_change × price`` 是申赎代理量
    （A 股 ETF 申赎一般 T+1 确认，但 price × shares 是当日推算的
    资金流向）。  ``premium_rate = (price - net_value) / net_value * 100``。
    """

    __tablename__ = "etf_fund_flow"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")

    ts_code = Column(
        String(20), nullable=False, index=True, comment="ETF 代码 (含后缀)"
    )
    trade_date = Column(Date, nullable=False, index=True, comment="交易日期")

    price = Column(Numeric(12, 4), comment="收盘价 (元)")
    net_value = Column(Numeric(12, 4), comment="IOPV / 单位净值 (元)")
    premium_rate = Column(Numeric(8, 4), comment="折溢价率 (%)")
    shares_outstanding = Column(Numeric(20, 4), comment="总份额 (份)")
    shares_change = Column(Numeric(20, 4), comment="当日份额变化 (份)")
    turnover = Column(Numeric(20, 4), comment="成交额 (元)")
    inferred_net_inflow = Column(
        Numeric(20, 4),
        comment="推算资金净流入 (元) ≈ shares_change × price",
    )

    fetched_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="抓取时间",
    )

    __table_args__ = (
        UniqueConstraint(
            "ts_code", "trade_date",
            name="uq_etf_fund_flow_ts_code_date",
        ),
        Index(
            "ix_etf_fund_flow_inferred_net",
            "trade_date", "inferred_net_inflow",
        ),
    )


# ---------------------------------------------------------------------------
# 4. 综合资金信号
# ---------------------------------------------------------------------------


class FlowSignal(Base):
    """综合资金信号 (按日)。

    聚合多源 (akshare 个股资金流 / 融资 / 龙虎榜 / 股东户数 / AH 溢价 /
    大宗交易)，输出 ``composite_score ∈ [-100, +100]`` 和 JSONB
    ``score_breakdown`` 各分量贡献明细。
    """

    __tablename__ = "flow_signal"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")

    ts_code = Column(
        String(20), nullable=False, index=True, comment="证券代码 (含后缀)"
    )
    trade_date = Column(Date, nullable=False, index=True, comment="交易日期")

    # 直接信号
    main_net_inflow = Column(
        Numeric(20, 4),
        comment="主力资金净流入 (元) (来自 individual_fund_flow)",
    )

    # 间接信号
    margin_net_change = Column(
        Numeric(20, 4), comment="融资余额日变化 (元) — 正=融资买入加杠杆"
    )
    lhb_net_buy = Column(
        Numeric(20, 4),
        comment="龙虎榜机构净买额 (元) — 当日有龙虎榜时写入",
    )
    shareholder_count_change = Column(
        Numeric(20, 4),
        comment="股东户数环比变化 (户) — 负数=筹码集中, 正=筹码分散",
    )
    ah_premium = Column(
        Numeric(8, 4),
        comment="AH 溢价率 (%) — 仅 A+H 同时上市的股票",
    )
    block_trade_net = Column(
        Numeric(20, 4),
        comment="大宗交易净买额 (元) — 买方-卖方 (负=净卖)",
    )

    # 综合评分
    composite_score = Column(
        Numeric(8, 4),
        comment="综合资金情绪评分 [-100, +100]；正=资金净流入，负=资金净流出",
    )
    score_breakdown = Column(
        JSON,
        comment="各分量贡献明细: { main, margin, lhb, shareholder, ah, block }",
    )

    fetched_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="抓取时间",
    )

    __table_args__ = (
        UniqueConstraint(
            "ts_code", "trade_date",
            name="uq_flow_signal_ts_code_date",
        ),
        Index(
            "ix_flow_signal_composite",
            text("composite_score DESC"),
        ),
    )
