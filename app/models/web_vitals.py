"""Web Vitals ingestion model.

Captures Core Web Vitals (LCP / INP / CLS / FCP / TTFB) reported by the
frontend's ``web-vitals`` library via ``navigator.sendBeacon`` /
``fetch(keepalive: true)``. The endpoint is intentionally best-effort —
a slow / unreachable backend must NEVER throw on the client, so the
route swallows DB errors and returns 204.

Why a dedicated table (vs. dumping into the audit_log):
* High write volume — one row per real-user interaction. Mixing this with
  the admin audit log would make weekly retention cleanup painful.
* Aggregations are different — p75 over 24h grouped by name + rating
  counts. Easier with a dedicated schema.
"""

from sqlalchemy import BigInteger, Column, DateTime, Float, ForeignKey, Integer, String, func

from app.core.database import Base


class WebVitalsLog(Base):
    """Single Web Vitals observation reported by the browser."""

    __tablename__ = "web_vitals_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True, comment="ID")
    name = Column(
        String(16),
        nullable=False,
        index=True,
        comment="Vital name: LCP / INP / CLS / FCP / TTFB",
    )
    value = Column(
        Float,
        nullable=False,
        comment="Reported value (ms for LCP/INP/FCP/TTFB, unitless for CLS)",
    )
    rating = Column(
        String(8),
        nullable=False,
        comment="web-vitals rating: good / needs-improvement / poor",
    )
    page = Column(
        String(256),
        nullable=True,
        index=True,
        comment="Optional page path/identifier (window.location.pathname)",
    )
    navigation_type = Column(
        String(32),
        nullable=True,
        comment="PerformanceNavigationTiming.type (navigate / reload / …)",
    )
    # NB: named ``vitals_id`` (NOT ``id_label`` / ``id``) so the Python
    # attribute and column never clash with the BigInteger primary key.
    vitals_id = Column(
        "vitals_id",
        String(64),
        nullable=True,
        comment="web-vitals 'id' attribute (e.g. 'v1-2026-07-16'), used to dedupe",
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="User who emitted the metric (null = anonymous)",
    )
    received_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
        comment="Server-side receive timestamp",
    )