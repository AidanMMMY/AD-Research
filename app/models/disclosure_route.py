"""上市公司信息披露路由知识库。

存储每家 A 股公司的定期报告 / 公告获取路径，包括：
- 交易所官方披露 URL（上证 / 深证 / 北证 / 巨潮）
- 公司官网投资者关系页面 URL
- 最近验证时间和状态

该表是 AD-Research 的数据源独立性基础设施——当第三方 API 不可用时，
系统可降级到直接访问公司官方披露渠道。
"""

from datetime import datetime, date

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
)

from app.core.database import Base


class CompanyDisclosureRoute(Base):
    """上市公司信息披露获取路径。"""

    __tablename__ = "company_disclosure_route"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # ---- 标识 ----
    code = Column(
        String(20),
        nullable=False,
        unique=True,
        comment="A 股代码（纯数字，如 600519）",
    )
    name = Column(String(200), nullable=False, comment="公司简称")

    # ---- 交易所披露 URL（结构化，可预测）----
    exchange_code = Column(
        String(10),
        nullable=False,
        comment="交易所代码: SSE / SZSE / BSE",
    )
    sse_disclosure_url = Column(
        Text,
        nullable=True,
        comment="上交所公告列表页 URL（仅 SSE 公司）",
    )
    szse_disclosure_url = Column(
        Text,
        nullable=True,
        comment="深交所公告列表页 URL（仅 SZSE 公司）",
    )
    cninfo_disclosure_url = Column(
        Text,
        nullable=True,
        comment="巨潮资讯网公告页 URL（大部分公司可用）",
    )

    # ---- 公司官网 IR 页面 ----
    ir_website_url = Column(
        Text,
        nullable=True,
        comment="公司官网投资者关系主页 URL（agent 发现）",
    )
    ir_discovery_method = Column(
        String(50),
        nullable=True,
        comment="IR URL 发现方式: web_search | manual | ai_inferred",
    )

    # ---- 验证状态 ----
    last_verified_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="最近一次成功验证时间",
    )
    verification_status = Column(
        String(20),
        server_default="pending",
        comment="验证状态: pending / verified / failed / stale",
    )
    verification_notes = Column(
        Text,
        nullable=True,
        comment="验证备注（失败原因等）",
    )

    # ---- 元数据 ----
    market_cap_rank = Column(
        Integer,
        nullable=True,
        comment="市值排名（NULL = 非 A 股或未排行）",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("idx_cdr_exchange", "exchange_code"),
        Index("idx_cdr_status", "verification_status"),
        Index("idx_cdr_rank", "market_cap_rank"),
    )
