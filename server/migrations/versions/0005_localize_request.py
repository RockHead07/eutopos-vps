"""localize_request: catatan tiap permintaan /localize (roadmap M1-6)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "localize_request",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result", sa.String(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("area_id", sa.String(), nullable=True),
        sa.Column("map_version", sa.Integer(), nullable=True),
        sa.Column("inliers", sa.Integer(), nullable=True),
        sa.Column("correspondences", sa.Integer(), nullable=True),
        sa.Column("intrinsics_source", sa.String(), nullable=True),
        sa.Column("t_s", sa.JSON(), nullable=True),
        sa.Column("wall_s", sa.Float(), nullable=True),
        sa.Column("image_w", sa.Integer(), nullable=True),
        sa.Column("image_h", sa.Integer(), nullable=True),
    )
    op.create_index("ix_localize_request_created_at", "localize_request", ["created_at"])


def downgrade():
    op.drop_table("localize_request")
