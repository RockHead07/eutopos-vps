"""room, route_edit, published_graph (dashboard rute otomatis)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-21
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "room",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("area_id", sa.String(), sa.ForeignKey("area.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("area_id", "name"),
    )
    op.create_index("ix_room_area_id", "room", ["area_id"])
    op.create_table(
        "route_edit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("area_id", sa.String(), sa.ForeignKey("area.id"), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("ax", sa.Float(), nullable=False),
        sa.Column("ay", sa.Float(), nullable=False),
        sa.Column("bx", sa.Float(), nullable=False),
        sa.Column("by", sa.Float(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_route_edit_area_id", "route_edit", ["area_id"])
    op.create_table(
        "published_graph",
        sa.Column("area_id", sa.String(), sa.ForeignKey("area.id"), primary_key=True),
        sa.Column("graph", sa.JSON(), nullable=False),
        sa.Column("published_by", sa.String(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("published_graph")
    op.drop_table("route_edit")
    op.drop_table("room")
