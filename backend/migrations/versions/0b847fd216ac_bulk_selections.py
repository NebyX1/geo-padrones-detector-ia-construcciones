"""Persistent rectangular selections, bounded analysis jobs and membership snapshots."""

from alembic import op
import sqlalchemy as sa

revision = "0b847fd216ac"
down_revision = "c93d1ae87502"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bulk_selections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("bounds", sa.JSON(), nullable=False),
        sa.Column("selection_filters", sa.JSON(), nullable=False),
        sa.Column("scene_id", sa.String(36), sa.ForeignKey("imagery_scenes.id"), nullable=False),
        sa.Column("model_version_id", sa.String(36), sa.ForeignKey("model_versions.id"), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("user_id", "idempotency_key"),
    )
    op.create_table(
        "bulk_selection_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("selection_id", sa.String(36), sa.ForeignKey("bulk_selections.id"), nullable=False),
        sa.Column("parcel_id", sa.String(36), sa.ForeignKey("parcels.id"), nullable=False),
        sa.Column("parcel_version_id", sa.String(36), sa.ForeignKey("cadastral_versions.id"), nullable=False),
        sa.Column("parcel_area_m2", sa.Float(), nullable=False),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id"), nullable=False),
        sa.UniqueConstraint("selection_id", "parcel_id"),
    )
    for column in ("selection_id", "parcel_id", "job_id"):
        op.create_index(f"ix_bulk_selection_items_{column}", "bulk_selection_items", [column])


def downgrade():
    op.drop_table("bulk_selection_items")
    op.drop_table("bulk_selections")
