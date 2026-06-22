"""ETF scoring and report metadata ORM models.

Contains tables for score templates, ETF composite scores, and report generation metadata.
"""

from sqlalchemy import (
    DECIMAL,
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


class ScoreTemplate(Base):
    """Score template definition table.

    Stores the weight configuration for each scoring dimension
    (return, risk, sharpe, liquidity, trend) as a JSON object.
    """

    __tablename__ = "score_template"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    name = Column(String(100), nullable=False, comment="Template name")
    description = Column(Text, comment="Template description")
    weights = Column(JSON, nullable=False, comment="Dimension weights as JSON")
    is_default = Column(
        Boolean,
        default=False,
        comment="Whether this is the default template",
    )
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

    __table_args__ = (
        Index("idx_score_template_default", "is_default"),
    )


class ETFScore(Base):
    """ETF composite score table.

    Stores daily composite scores and per-dimension sub-scores
    for each ETF, along with overall and category rankings.
    """

    __tablename__ = "etf_score"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    etf_code = Column(
        String(20),
        ForeignKey("etf_info.code", ondelete="CASCADE"),
        nullable=False,
        comment="ETF code",
    )
    trade_date = Column(Date, nullable=False, comment="Trade date")
    template_id = Column(
        Integer,
        ForeignKey("score_template.id", ondelete="CASCADE"),
        nullable=False,
        comment="Score template ID",
    )
    composite_score = Column(DECIMAL(8, 4), comment="Composite score")
    score_return = Column(DECIMAL(8, 4), comment="Return dimension score")
    score_risk = Column(DECIMAL(8, 4), comment="Risk dimension score")
    score_sharpe = Column(DECIMAL(8, 4), comment="Sharpe dimension score")
    score_liquidity = Column(DECIMAL(8, 4), comment="Liquidity dimension score")
    score_trend = Column(DECIMAL(8, 4), comment="Trend dimension score")
    rank_overall = Column(Integer, comment="Overall rank across all ETFs")
    rank_category = Column(Integer, comment="Rank within category")
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Creation time",
    )

    __table_args__ = (
        UniqueConstraint(
            "etf_code", "trade_date", "template_id",
            name="uq_etf_score_code_date_template",
        ),
        Index("idx_etf_score_date", "trade_date"),
        Index("idx_etf_score_template", "template_id"),
        Index("idx_etf_score_composite", "composite_score"),
    )


class ReportMetadata(Base):
    """Report generation metadata table.

    Tracks the lifecycle of generated reports including status,
    output format, file path, and timing information.
    """

    __tablename__ = "report_metadata"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    report_type = Column(
        String(50),
        nullable=False,
        comment="Report type (e.g. daily, weekly, monthly)",
    )
    report_date = Column(Date, nullable=False, comment="Report date")
    pool_id = Column(
        Integer,
        ForeignKey("etf_pools.id", ondelete="CASCADE"),
        comment="ETF pool ID",
    )
    template_id = Column(
        Integer,
        ForeignKey("score_template.id", ondelete="SET NULL"),
        comment="Score template ID",
    )
    status = Column(
        String(20),
        nullable=False,
        comment="Status: pending/running/success/failed",
    )
    format = Column(
        String(20),
        comment="Output format (e.g. pdf, html, xlsx)",
    )
    file_path = Column(String(500), comment="Generated file path")
    file_size = Column(Integer, comment="File size in bytes")
    error_msg = Column(Text, comment="Error message if failed")
    started_at = Column(DateTime(timezone=True), comment="Generation start time")
    finished_at = Column(DateTime(timezone=True), comment="Generation finish time")
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Creation time",
    )

    __table_args__ = (
        Index("idx_report_metadata_status", "status"),
        Index("idx_report_metadata_date", "report_date"),
        Index("idx_report_metadata_type", "report_type"),
    )
