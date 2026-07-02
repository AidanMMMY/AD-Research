"""merge phase 5/9 heads into a single linear chain

Revision ID: e2f3a4b5c6d7
Revises: c1d2e3f4a5b6, f8a9b0c1d2e3
Create Date: 2026-07-02 15:30:00.000000

The Phase 4/8 batch left two parallel branches after the
``b2c3d4e5f6a7`` merge:

  branch A: b2c3d4e5f6a7 → c1d2e3f4a5b6 (cninfo_reports)
  branch B: b2c3d4e5f6a7 → f8a9b0c1d2e3 (search_trends)

This merge collapses them into a single head so that
``alembic upgrade head`` works again.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = ("c1d2e3f4a5b6", "f8a9b0c1d2e3")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No schema change — pure merge of two parallel branches."""
    pass


def downgrade() -> None:
    """Split the two branches back apart."""
    pass
