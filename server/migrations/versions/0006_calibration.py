"""calibration: set kalibrasi, titik, pengamatan, dan riwayat penyelarasan (roadmap M1-2)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "calibration_set",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("area_id", sa.String(), sa.ForeignKey("area.id"), nullable=False),
        sa.Column("map_version_id", sa.Integer(), sa.ForeignKey("map_version.id"), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.String(), nullable=True),
    )
    op.create_index("ix_calibration_set_area_id", "calibration_set", ["area_id"])
    op.create_table(
        "calibration_point",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("set_id", sa.Integer(), sa.ForeignKey("calibration_set.id"), nullable=False),
        sa.Column("point_id", sa.String(), nullable=False),
        sa.Column("x_m", sa.Float(), nullable=False),
        sa.Column("y_m", sa.Float(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.UniqueConstraint("set_id", "point_id"),
    )
    op.create_index("ix_calibration_point_set_id", "calibration_point", ["set_id"])
    op.create_table(
        "calibration_observation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("set_id", sa.Integer(), sa.ForeignKey("calibration_set.id"), nullable=False),
        sa.Column("point_id", sa.String(), nullable=False),
        sa.Column("model_xyz", sa.JSON(), nullable=False),
        sa.Column("inliers", sa.Integer(), nullable=False),
        sa.Column("heading_deg", sa.Float(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("query", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_calibration_observation_set_id", "calibration_observation", ["set_id"])
    op.create_table(
        "alignment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("map_version_id", sa.Integer(), sa.ForeignKey("map_version.id"), nullable=False),
        sa.Column("set_id", sa.Integer(), sa.ForeignKey("calibration_set.id"), nullable=True),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("stats", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_alignment_map_version_id", "alignment", ["map_version_id"])
    op.create_index(
        "one_applied_per_version",
        "alignment",
        ["map_version_id"],
        unique=True,
        postgresql_where=sa.text("status = 'applied'"),
        sqlite_where=sa.text("status = 'applied'"),
    )


def downgrade():
    op.drop_table("alignment")
    op.drop_table("calibration_observation")
    op.drop_table("calibration_point")
    op.drop_table("calibration_set")
