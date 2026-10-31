"""One-use numeric login captcha alongside two-factor authentication."""

from alembic import op
import sqlalchemy as sa

revision = "c93d1ae87502"
down_revision = "f2a08bc931d7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "login_captchas",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("browser_digest", sa.String(64), nullable=False),
        sa.Column("answer_digest", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_login_captchas_browser_digest", "login_captchas", ["browser_digest"])
    op.create_index("ix_login_captchas_expires_at", "login_captchas", ["expires_at"])


def downgrade():
    op.drop_table("login_captchas")
