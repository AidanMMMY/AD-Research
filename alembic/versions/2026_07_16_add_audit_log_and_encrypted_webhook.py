"""add audit_log table + encrypted webhook_url column

Revision ID: 2026_07_16_add_audit_log_and_encrypted_webhook
Revises: 2026_07_14_create_fund_flow_tables
Create Date: 2026-07-16

P0 batch (2026-07-16):

1. ``audit_log`` — captures every admin write (POST / PUT / PATCH /
   DELETE on admin routers).  Columns mirror the model:
     - actor_user_id, actor_username, action, target_type, target_id,
       payload_diff (JSONB), ip, status_code, detail, created_at.
   Indexed on (created_at DESC) and (actor_user_id, created_at DESC) so
   admin dashboards can page recent activity without a full scan.

2. ``notification_config.webhook_url_encrypted`` — dedicated Fernet-
   encrypted text column for the webhook URL.  New rows write here
   instead of ``config_json["webhook_url"]``; legacy plaintext rows
   remain readable until the next update.  Kept nullable so the
   migration is safe on tables that already hold data.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "2026_07_16_add_audit_log_and_encrypted_webhook"
down_revision = "2026_07_14_create_fund_flow_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. audit_log table
    # ------------------------------------------------------------------
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "actor_user_id",
            sa.Integer(),
            nullable=True,
            comment="User who performed the action (null = anonymous / scheduler)",
        ),
        sa.Column(
            "actor_username",
            sa.String(length=50),
            nullable=True,
            comment="Cached username for display",
        ),
        sa.Column(
            "action",
            sa.String(length=40),
            nullable=False,
            comment="HTTP method + endpoint slug, e.g. POST /admin/users",
        ),
        sa.Column(
            "target_type",
            sa.String(length=40),
            nullable=True,
            comment="Resource class, e.g. 'user', 'notification_config'",
        ),
        sa.Column(
            "target_id",
            sa.String(length=80),
            nullable=True,
            comment="Resource id (string for portability, e.g. '42')",
        ),
        sa.Column(
            "payload_diff",
            sa.JSON(),
            nullable=True,
            comment="Request body (sanitized) — keys changed and their new values",
        ),
        sa.Column(
            "ip",
            sa.String(length=64),
            nullable=True,
            comment="Client IP (X-Forwarded-For first hop if present)",
        ),
        sa.Column(
            "status_code",
            sa.Integer(),
            nullable=True,
            comment="HTTP response status (when available)",
        ),
        sa.Column(
            "detail",
            sa.String(length=500),
            nullable=True,
            comment="Free-form description or short error message",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="When the action was performed",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
    )
    op.create_index(
        "ix_audit_log_created_at_desc",
        "audit_log",
        [sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_audit_log_actor_user_id_created_at",
        "audit_log",
        ["actor_user_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_audit_log_action",
        "audit_log",
        ["action"],
    )

    # ------------------------------------------------------------------
    # 2. notification_config.webhook_url_encrypted
    # ------------------------------------------------------------------
    op.add_column(
        "notification_config",
        sa.Column(
            "webhook_url_encrypted",
            sa.Text(),
            nullable=True,
            comment="Fernet-encrypted webhook URL (P0-3)",
        ),
    )


def downgrade() -> None:
    op.drop_column("notification_config", "webhook_url_encrypted")
    op.drop_index("ix_audit_log_action", table_name="audit_log")
    op.drop_index("ix_audit_log_actor_user_id_created_at", table_name="audit_log")
    op.drop_index("ix_audit_log_created_at_desc", table_name="audit_log")
    op.drop_table("audit_log")