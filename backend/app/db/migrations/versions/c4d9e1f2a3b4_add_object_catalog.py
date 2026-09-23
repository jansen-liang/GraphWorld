"""add object catalog

Revision ID: c4d9e1f2a3b4
Revises: b3a8f7d4c2e1
"""

from alembic import op
import sqlalchemy as sa


revision = "c4d9e1f2a3b4"
down_revision = "b3a8f7d4c2e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "object_catalog",
        sa.Column("semantic_type", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("name_cn", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("width_cm", sa.Float(), nullable=False),
        sa.Column("depth_cm", sa.Float(), nullable=False),
        sa.Column("height_cm", sa.Float(), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("state_schema", sa.JSON(), nullable=False),
        sa.Column("default_states", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("semantic_type"),
    )
    op.create_index(op.f("ix_object_catalog_is_active"), "object_catalog", ["is_active"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_object_catalog_is_active"), table_name="object_catalog")
    op.drop_table("object_catalog")
