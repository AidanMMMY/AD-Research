"""add_strategy_type_index

Revision ID: 997c17ed0dfd
Revises: b2_news_schema_enrich
Create Date: 2026-07-01 13:43:06.218812

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '997c17ed0dfd'
down_revision: Union[str, Sequence[str], None] = 'b2_news_schema_enrich'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        "idx_strategy_config_type",
        "strategy_config",
        ["strategy_type"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_strategy_config_type", table_name="strategy_config")
