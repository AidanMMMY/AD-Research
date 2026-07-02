"""Cninfo (巨潮资讯) periodic report models.

Stores metadata + extracted text for A-share periodic reports
(annual / semi-annual / Q1 / Q3) fetched from the public cninfo
``hisAnnouncement/query`` endpoint.  PDFs are downloaded to
``${CNINFO_PDF_DIR}/{ts_code}/{announcement_id}.pdf`` and a short
text excerpt is stored alongside the metadata for search / preview.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)

from app.core.database import Base


class CninfoReport(Base):
    """A single periodic report announcement from cninfo.

    Unique key is the upstream ``announcementId`` (cninfo 公告 ID).
    Idempotent upserts are done on conflict of that column.
    """

    __tablename__ = "cninfo_reports"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    ts_code = Column(String(20), nullable=False, comment="Tushare 证券代码 (e.g. 600519.SH)")
    stock_code = Column(String(20), nullable=False, comment="Stock 6-digit code (e.g. 600519)")
    org_id = Column(String(32), nullable=True, comment="Cninfo orgId")
    sec_code = Column(String(32), nullable=True, comment="Cninfo secCode")
    announcement_id = Column(
        String(64), nullable=False, comment="Cninfo 公告 ID (e.g. 1234567890)"
    )
    announcement_title = Column(
        String(512), nullable=False, comment="公告标题 (e.g. '中国平安2025年年度报告')"
    )
    adjunct_url = Column(
        String(512), nullable=False, comment="PDF 下载链接 (相对路径 static cninfo.com.cn)"
    )
    file_path = Column(String(1024), nullable=True, comment="本地 PDF 存储路径 (相对 PDF_DIR)")
    file_size = Column(BigInteger, nullable=True, comment="PDF 文件大小 (bytes)")
    announcement_time = Column(
        DateTime(timezone=True), nullable=False, comment="公告发布时间"
    )
    adjunct_type = Column(
        String(32), nullable=False, comment="附件类型: annual/semi/q1/q3/other"
    )
    is_periodic = Column(
        Boolean, nullable=False, server_default="false", comment="是否定期报告"
    )
    fiscal_year = Column(Integer, nullable=True, comment="财年 (e.g. 2025)")
    fiscal_quarter = Column(
        Integer, nullable=True, comment="财季: 1=Q1, 2=半年报, 3=Q3, 4=年报"
    )
    extracted_text = Column(Text, nullable=True, comment="PDF 提取出的文本 (截断)")
    extraction_status = Column(
        String(16),
        nullable=False,
        server_default="pending",
        comment="文本提取状态: pending/downloading/extracted/failed",
    )
    extracted_at = Column(
        DateTime(timezone=True), nullable=True, comment="文本提取完成时间"
    )
    source = Column(
        String(32), nullable=False, server_default="cninfo", comment="数据来源"
    )
    raw_payload = Column(Text, nullable=True, comment="上游公告 JSON 字符串 (debug)")
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
        UniqueConstraint("announcement_id", name="uq_cninfo_reports_announcement_id"),
        Index("ix_cninfo_reports_ts_code", "ts_code"),
        Index("ix_cninfo_reports_stock_code", "stock_code"),
        Index("ix_cninfo_reports_announcement_time", "announcement_time"),
        Index("ix_cninfo_reports_is_periodic", "is_periodic"),
        Index(
            "ix_cninfo_reports_periodic_quarter",
            "fiscal_year",
            "fiscal_quarter",
            "adjunct_type",
        ),
    )
