"""organization, building: hierarki gedung sebagai induk tiap area (tahap 1)

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-18
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "organization",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
    )
    op.create_index("ix_organization_slug", "organization", ["slug"], unique=True)

    op.create_table(
        "building",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "org_id", sa.Integer(), sa.ForeignKey("organization.id"), nullable=False
        ),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.UniqueConstraint("org_id", "slug"),
    )
    op.create_index("ix_building_org_id", "building", ["org_id"])
    op.create_index("ix_building_slug", "building", ["slug"])

    # Sisipkan organisasi bawaan dan gedung HCM
    op.execute(
        "INSERT INTO organization (slug, name) VALUES ('default', 'Organisasi bawaan')"
    )
    op.execute(
        "INSERT INTO building (org_id, slug, name) "
        "SELECT id, 'hcm', 'HCM' FROM organization WHERE slug = 'default'"
    )

    # Tambah kolom building_id pada area
    with op.batch_alter_table("area") as batch_op:
        batch_op.add_column(
            sa.Column(
                "building_id",
                sa.Integer(),
                nullable=True,
            )
        )

    op.execute(
        "UPDATE area SET building_id = (SELECT id FROM building WHERE slug = 'hcm' LIMIT 1)"
    )

    with op.batch_alter_table("area") as batch_op:
        batch_op.alter_column(
            "building_id",
            existing_type=sa.Integer(),
            nullable=False,
            existing_nullable=True,
        )
        batch_op.create_foreign_key(
            "fk_area_building_id_building", "building", ["building_id"], ["id"]
        )
        batch_op.create_index("ix_area_building_id", ["building_id"])


def downgrade():
    with op.batch_alter_table("area") as batch_op:
        batch_op.drop_index("ix_area_building_id")
        batch_op.drop_constraint("fk_area_building_id_building", type_="foreignkey")
        batch_op.drop_column("building_id")
    op.drop_table("building")
    op.drop_table("organization")
