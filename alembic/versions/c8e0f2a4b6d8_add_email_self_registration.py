"""add email self-registration support

邮箱自助注册（2026-10-25 设计 §3.1）：
- ``users`` 加 ``email``（UNIQUE 索引，允许多个 NULL，存量用户不强制补绑）与
  ``email_verified_at``；
- 新表 ``email_verifications``：验证码 sha256 哈希 + 10min TTL + 尝试计数。

Revision ID: c8e0f2a4b6d8
Revises: b3c5d7e9f1a2
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8e0f2a4b6d8"
down_revision: str | Sequence[str] | None = "b3c5d7e9f1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email", sa.String(length=255), nullable=True, comment="Account email"),
    )
    op.add_column(
        "users",
        sa.Column(
            "email_verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the account email was verified",
        ),
    )
    # 唯一索引而非 UNIQUE 约束：名字与 ORM 一致，且 PostgreSQL/SQLite 均允许多个 NULL。
    op.create_index("uq_users_email", "users", ["email"], unique=True)

    op.create_table(
        "email_verifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="Row ID"),
        sa.Column(
            "user_id",
            sa.Integer(),
            nullable=False,
            comment="Owner user",
        ),
        sa.Column(
            "code_hash",
            sa.String(length=64),
            nullable=False,
            comment="SHA-256 of the 6-digit code",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Code TTL (10 min)",
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="Failed verification attempts",
        ),
        sa.Column(
            "consumed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Used / superseded at",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="Creation time",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_verifications_user_id", "email_verifications", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_email_verifications_user_id", table_name="email_verifications")
    op.drop_table("email_verifications")
    op.drop_index("uq_users_email", table_name="users")
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "email")
