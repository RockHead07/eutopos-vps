"""splat_job: antrean splat per versi peta

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-09
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "splat_job",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "map_version_id",
            sa.Integer(),
            sa.ForeignKey("map_version.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("stage", sa.String(), nullable=True),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("map_version_id"),
    )


def downgrade():
    op.drop_table("splat_job")
