"""widen news_article.source_id to varchar(500)

The wechat2rss public-mirror feeds (90 accounts, see
``app/services/news/sources/wechat2rss_batch.py``) identify items by the
full query-form ``mp.weixin.qq.com/s?__biz=...&mid=...&idx=1&sn=...&
chksm=...&scene=...`` URL (~250 chars). ``source_id`` was varchar(200),
so every insert for those feeds failed with
``StringDataRightTruncation`` and ~15 accounts never landed in
``news_article`` (2026-07-27, runbook
``docs/dev-notes/20260727-news-source-expansion.md`` §3.3).

url is already varchar(1000); source_id holds the same class of value
for RSS sources, so widen it to 500. Pure metadata change in Postgres
(varchar widening does not rewrite the table).

Revision ID: s5t7u9v1w3x5
Revises: r4s6t8u0v2w4
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "s5t7u9v1w3x5"
down_revision: str | Sequence[str] | None = "r4s6t8u0v2w4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "news_article",
        "source_id",
        existing_type=sa.String(length=200),
        type_=sa.String(length=500),
        existing_nullable=False,
        existing_comment="Source-native id (guid, sec accession, reddit id)",
    )


def downgrade() -> None:
    op.alter_column(
        "news_article",
        "source_id",
        existing_type=sa.String(length=500),
        type_=sa.String(length=200),
        existing_nullable=False,
        existing_comment="Source-native id (guid, sec accession, reddit id)",
    )
