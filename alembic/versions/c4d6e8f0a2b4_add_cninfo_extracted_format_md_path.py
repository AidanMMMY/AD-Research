"""add cninfo extracted_format and md_path columns

cninfo PDF→Markdown 提取管线升级（2026-08-03，B2）：``cninfo_reports``
新增两列：

* ``extracted_format`` — 提取产物格式：``'text'``（旧 pdfplumber
  纯文本）/ ``'md'``（pymupdf4llm markdown）；``NULL`` = 旧数据
  （尚未区分格式，等同于 text 时代遗留）。
* ``md_path`` — markdown 存档文件路径（相对 ``CNINFO_MD_DIR``），
  DB 的 ``extracted_text`` 仍是主存储，文件只是存档副本。

Revision ID: c4d6e8f0a2b4
Revises: b7d9f1h3j5l7
Create Date: 2026-08-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d6e8f0a2b4"
down_revision: Union[str, Sequence[str], None] = "b7d9f1h3j5l7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cninfo_reports",
        sa.Column(
            "extracted_format",
            sa.String(length=16),
            nullable=True,
            comment="提取格式: text/md，NULL=旧数据",
        ),
    )
    op.add_column(
        "cninfo_reports",
        sa.Column(
            "md_path",
            sa.String(length=1024),
            nullable=True,
            comment="Markdown 存档路径（相对 MD_DIR）",
        ),
    )


def downgrade() -> None:
    op.drop_column("cninfo_reports", "md_path")
    op.drop_column("cninfo_reports", "extracted_format")
