"""add email_verifications.purpose (register | password_reset)

忘记密码链路（2026-10-25）：同一张 ``email_verifications`` 表复用为两套
验证码发放流。``purpose`` 列区分注册验证与密码重置，存量行经 server
default 全部落为 'register'，注册链路语义不变；新链路写
'password_reset'，消费端一律按 purpose 过滤，重置码不可能被拿去
/verify-registration 兑换（反之亦然）。

Revision ID: e6a8c0d2f4b6
Revises: c8e0f2a4b6d8
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e6a8c0d2f4b6"
down_revision: str | Sequence[str] | None = "c8e0f2a4b6d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "email_verifications",
        sa.Column(
            "purpose",
            sa.String(length=20),
            nullable=False,
            server_default="register",
            comment="Issuance flow: register | password_reset",
        ),
    )


def downgrade() -> None:
    op.drop_column("email_verifications", "purpose")
