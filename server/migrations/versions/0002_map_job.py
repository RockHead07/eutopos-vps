"""map_job dan map_version.published_by

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-01
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("map_version", sa.Column("published_by", sa.String(), nullable=True))
    op.create_table(
        "map_job",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("area_id", sa.String(), sa.ForeignKey("area.id"), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("stage", sa.String(), nullable=True),
        sa.Column("videos", sa.JSON(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("map_version_id", sa.Integer(), sa.ForeignKey("map_version.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_map_job_area_id", "map_job", ["area_id"])


def downgrade():
    op.drop_table("map_job")
    op.drop_column("map_version", "published_by")
