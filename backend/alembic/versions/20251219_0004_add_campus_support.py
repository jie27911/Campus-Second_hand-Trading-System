"""Add campus support for multi-campus trading

Revision ID: 20251219_0004
Revises: 20251219_0003
Create Date: 2025-12-19 13:30:00.000000
"""

from typing import Union, Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20251219_0004"
down_revision: Union[str, None] = "20251219_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create campuses table
    op.create_table(
        "campuses",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("sync_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("address", sa.String(length=200), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, default=0),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code")
    )

    # Add campus_id column to items table
    op.add_column("items", sa.Column("campus_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_items_campus_id",
        "items",
        "campuses",
        ["campus_id"],
        ["id"]
    )
    op.create_index("ix_items_campus_id", "items", ["campus_id"])

    # Insert default campuses
    op.execute("""
    INSERT INTO campuses (id, name, code, address, description, is_active, sort_order, created_at, updated_at, sync_version) VALUES
    (1, '本部校区', 'main', '大学本部', '主校区，包含大部分教学楼和宿舍', 1, 1, NOW(), NOW(), 1),
    (2, '南校区', 'south', '大学南校区', '南校区，包含理工科专业', 1, 2, NOW(), NOW(), 1),
    (3, '北校区', 'north', '大学北校区', '北校区，包含文科专业', 1, 3, NOW(), NOW(), 1)
    """)


def downgrade() -> None:
    # Remove campus_id column from items table
    op.drop_index("ix_items_campus_id", table_name="items")
    op.drop_constraint("fk_items_campus_id", "items", type_="foreignkey")
    op.drop_column("items", "campus_id")

    # Drop campuses table
    op.drop_table("campuses")