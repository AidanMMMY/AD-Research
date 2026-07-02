"""merge heads research reports + futures tables

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f8, f7a8b9c0d1e2
Create Date: 2026-07-02 14:00:00.000000

Merge the two heads introduced by Phase 8 (research_reports + futures)
so that subsequent Phase 6/7/9 migrations have a single linear
down_revision target.
"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = ("a1b2c3d4e5f8", "f7a8b9c0d1e2")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op merge migration — both parents must already be applied."""
    pass


def downgrade() -> None:
    """No-op merge migration."""
    pass