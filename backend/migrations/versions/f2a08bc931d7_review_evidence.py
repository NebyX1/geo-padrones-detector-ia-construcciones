"""Private review evidence and reanalysis requests."""

from alembic import op
import sqlalchemy as sa

revision = "f2a08bc931d7"
down_revision = "dab77c1e40e5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "review_cases", sa.Column("needs_reanalysis", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.alter_column("review_cases", "needs_reanalysis", server_default=None)
    op.create_table(
        "review_attachments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("case_id", sa.String(36), sa.ForeignKey("review_cases.id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("mime", sa.String(80), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
    )
    op.create_index("ix_review_attachments_case_id", "review_attachments", ["case_id"])


def downgrade():
    op.drop_table("review_attachments")
    op.drop_column("review_cases", "needs_reanalysis")
