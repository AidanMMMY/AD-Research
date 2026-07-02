"""Macro-economic indicator ORM model.

Stores time-series observations for macro indicators from various
sources (FRED for US, NBS/PBOC for CN, etc.). The table is shared by
all macro sources; ``source`` + ``code`` + ``region`` + ``period`` form
the idempotency key.
"""

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)

from app.core.database import Base


class MacroIndicator(Base):
    """One macro-indicator observation.

    A row represents a single value published by an external data source
    for a given indicator at a given period (date for daily/weekly
    series, or first-of-month for monthly series).

    Composite uniqueness on (code, region, period, source) makes the
    refresh path idempotent: re-running the same refresh on the same
    date updates the existing row instead of creating duplicates.
    """

    __tablename__ = "macro_indicator"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="ID")

    # Logical identifier: a stable short code independent of the data
    # source's own series id (e.g. ``us_cpi`` rather than ``CPIAUCSL``).
    code = Column(String(80), nullable=False, index=True, comment="Indicator code")

    # Region / market scope: ``us``, ``cn``, ``global``, etc.
    region = Column(String(20), nullable=False, index=True, comment="Region code")

    # Human-readable Chinese label used in the frontend.
    name_zh = Column(String(120), nullable=False, comment="Indicator Chinese name")

    # Optional English name for international display.
    name_en = Column(String(120), nullable=True, comment="Indicator English name")

    # Display unit (e.g. 十亿美元, %, 指数).
    unit = Column(String(40), nullable=False, default="", comment="Display unit")

    # Period — for daily/weekly series this is a date; for monthly/quarterly
    # series we still store it as a date (the first day of the period), which
    # keeps the chart x-axis consistent across frequencies.
    period = Column(Date, nullable=False, comment="Observation date")

    value = Column(Float, nullable=False, comment="Numeric value")

    # Data source tag: ``fred``, ``nbs``, ``pboc``, etc.
    source = Column(
        String(20),
        nullable=False,
        server_default="fred",
        comment="Data source",
    )

    fetched_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment="When this row was last upserted",
    )

    __table_args__ = (
        UniqueConstraint(
            "code", "region", "period", "source",
            name="uq_macro_indicator_code_region_period_source",
        ),
        Index("ix_macro_indicator_region_code", "region", "code"),
        Index("ix_macro_indicator_code_period", "code", "period"),
    )