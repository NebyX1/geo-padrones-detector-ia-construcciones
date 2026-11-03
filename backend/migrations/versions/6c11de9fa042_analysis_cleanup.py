"""Durable deletion of analysis objects and queue records."""

from alembic import op
import sqlalchemy as sa

revision = "6c11de9fa042"
down_revision = "0b847fd216ac"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cleanup_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.UniqueConstraint("kind", "key"),
    )


def downgrade():
    op.drop_table("cleanup_entries")
