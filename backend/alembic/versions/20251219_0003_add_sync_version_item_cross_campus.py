"""Add sync_version to item_cross_campus

Revision ID: 20251219_0003
Revises: d23b17088903
Create Date: 2025-12-19 12:30:00.000000
"""

from typing import Union, Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20251219_0003"
down_revision: Union[str, None] = "d23b17088903"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "item_cross_campus",
        sa.Column("sync_version", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("item_cross_campus", "sync_version")
