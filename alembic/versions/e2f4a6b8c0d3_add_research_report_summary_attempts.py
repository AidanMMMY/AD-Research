"""add summary_attempts column to research_reports

Retry bookkeeping for the LLM summary drain (2026-10-12), mirroring
``news_article.summary_attempts`` (d1e3f5a7b9c1). The batch job selects
``summary IS NULL`` rows; rows whose LLM call kept failing (provider
quota windows, unparseable output) stayed in the selection set forever
and were re-burned every 2h tick with no cap. Each attempt now
increments the counter and the drain excludes rows at the cap (3).

Revision ID: e2f4a6b8c0d3
Revises: d1e3f5a7b9c1
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2f4a6b8c0d3"
down_revision: str | Sequence[str] | None = "d1e3f5a7b9c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "research_reports",
        sa.Column(
            "summary_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="LLM 摘要失败次数；达到封顶后批次任务跳过该行（防永久重试烧钱）",
        ),
    )


def downgrade() -> None:
    op.drop_column("research_reports", "summary_attempts")
