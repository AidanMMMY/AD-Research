"""add must_change_password column to users

用户管理增强（2026-10-24）：新建用户自动生成随机密码 + 首次登录强制改密。
``users.must_change_password`` 为 True 时，前端跳转 /change-password，
后端仅放行 me/change-password/logout；改密成功后清回 False。

server_default=false 保证存量用户不受影响（无需回填）。

Revision ID: b3c5d7e9f1a2
Revises: e2f4a6b8c0d3
Create Date: 2026-10-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3c5d7e9f1a2"
down_revision: str | Sequence[str] | None = "e2f4a6b8c0d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="首次登录/重置后是否强制修改密码",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "must_change_password")
