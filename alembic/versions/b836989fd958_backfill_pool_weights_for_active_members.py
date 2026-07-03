"""backfill_pool_weights_for_active_members

Revision ID: b836989fd958
Revises: e2f3a4b5c6d7
Create Date: 2026-07-04 00:15:31.985284

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b836989fd958'
down_revision: Union[str, Sequence[str], None] = 'e2f3a4b5c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Backfill default weight records for active pool members without one."""
    op.execute("""
        INSERT INTO pool_weight (pool_id, etf_code, target_weight, weight_source, removed_at)
        SELECT
            pm.pool_id,
            pm.etf_code,
            0.0,
            'manual',
            NULL
        FROM pool_member pm
        WHERE pm.removed_at IS NULL
          AND NOT EXISTS (
              SELECT 1
              FROM pool_weight pw
              WHERE pw.pool_id = pm.pool_id
                AND pw.etf_code = pm.etf_code
                AND pw.removed_at IS NULL
          )
    """)


def downgrade() -> None:
    """Remove auto-created default weight records."""
    op.execute("""
        DELETE FROM pool_weight
        WHERE target_weight = 0.0
          AND weight_source = 'manual'
          AND removed_at IS NULL
    """)
