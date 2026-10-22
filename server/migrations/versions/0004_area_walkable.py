"""walkable_stroke dan kolom walkable di published_graph (area walkable)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-21
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "walkable_stroke",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("area_id", sa.String(), sa.ForeignKey("area.id"), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("radius", sa.Float(), nullable=False),
        sa.Column("points", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_walkable_stroke_area_id", "walkable_stroke", ["area_id"])
    op.add_column("published_graph", sa.Column("walkable", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("published_graph", "walkable")
    op.drop_table("walkable_stroke")
