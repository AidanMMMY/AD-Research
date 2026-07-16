"""add web_vitals_log table

Revision ID: 2026_07_16_add_web_vitals_log
Revises: 2026_07_16_add_audit_log_and_encrypted_webhook
Create Date: 2026-07-16

Frontend performance telemetry — one row per Core Web Vitals observation
(LCP / INP / CLS / FCP / TTFB) sent from the browser via
``navigator.sendBeacon``. The ingestion endpoint is best-effort; this
table is purely additive and never blocks user-facing requests.

Indexes:
* ``ix_web_vitals_log_name_received_at_desc`` — covers the 24h
  per-metric p50/p75/p95 aggregation in the admin summary endpoint.
* ``ix_web_vitals_log_name`` + ``ix_web_vitals_log_page`` — basic
  per-name / per-page lookup.
* ``ix_web_vitals_log_user_id`` — per-user telemetry joins.
* ``ix_web_vitals_log_received_at`` — recent-rows scan.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "2026_07_16_add_web_vitals_log"
down_revision = "2026_07_16_add_audit_log_and_encrypted_webhook"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "web_vitals_log",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
            comment="ID",
        ),
        sa.Column(
            "name",
            sa.String(length=16),
            nullable=False,
            comment="Vital name: LCP / INP / CLS / FCP / TTFB",
        ),
        sa.Column(
            "value",
            sa.Float(),
            nullable=False,
            comment="Reported value (ms for LCP/INP/FCP/TTFB, unitless for CLS)",
        ),
        sa.Column(
            "rating",
            sa.String(length=8),
            nullable=False,
            comment="web-vitals rating: good / needs-improvement / poor",
        ),
        sa.Column(
            "page",
            sa.String(length=256),
            nullable=True,
            comment="Optional page path/identifier (window.location.pathname)",
        ),
        sa.Column(
            "navigation_type",
            sa.String(length=32),
            nullable=True,
            comment="PerformanceNavigationTiming.type (navigate / reload / …)",
        ),
        sa.Column(
            "vitals_id",
            sa.String(length=64),
            nullable=True,
            comment="web-vitals 'id' attribute (e.g. 'v1-2026-07-16'), used to dedupe",
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            nullable=True,
            comment="User who emitted the metric (null = anonymous)",
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="Server-side receive timestamp",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_web_vitals_log"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_web_vitals_log_user_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_web_vitals_log_name_received_at_desc",
        "web_vitals_log",
        ["name", sa.text("received_at DESC")],
    )
    op.create_index(
        "ix_web_vitals_log_name", "web_vitals_log", ["name"]
    )
    op.create_index(
        "ix_web_vitals_log_page", "web_vitals_log", ["page"]
    )
    op.create_index(
        "ix_web_vitals_log_user_id", "web_vitals_log", ["user_id"]
    )
    op.create_index(
        "ix_web_vitals_log_received_at",
        "web_vitals_log",
        ["received_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_web_vitals_log_received_at", table_name="web_vitals_log")
    op.drop_index("ix_web_vitals_log_user_id", table_name="web_vitals_log")
    op.drop_index("ix_web_vitals_log_page", table_name="web_vitals_log")
    op.drop_index("ix_web_vitals_log_name", table_name="web_vitals_log")
    op.drop_index(
        "ix_web_vitals_log_name_received_at_desc", table_name="web_vitals_log"
    )
    op.drop_table("web_vitals_log")