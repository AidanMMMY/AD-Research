"""ETF market scan log model."""

from sqlalchemy import JSON, Column, Date, DateTime, Integer, String, func

from app.core.database import Base


class ETFScanLog(Base):
    """Log of ETF market scan results."""

    __tablename__ = "etf_scan_log"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")
    scan_date = Column(Date, nullable=False, comment="Scan date")
    new_count = Column(Integer, default=0, comment="Number of new ETFs found")
    delisted_count = Column(Integer, default=0, comment="Number of delisted ETFs found")
    changed_count = Column(Integer, default=0, comment="Number of changed ETFs found")
    details = Column(JSON, comment="Scan details as JSON")
    status = Column(
        String(20),
        default="success",
        comment="Status: success/failed",
    )
    error_msg = Column(String(500), comment="Error message if failed")
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="Creation time",
    )
