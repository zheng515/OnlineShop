"""Customer accounts and email (SRS rev. 8).

- users.email (lower case, unique when set) and users.email_verified_at (FR89, FR90).
- Usernames unique regardless of letter case (FR89).
- user_tokens: hashed, single-use email confirmation and password reset tokens (FR93).
- email_outbox: emails waiting to be sent, written in the same transaction as their event (FR95).
- rate_events: requests counted by the abuse limits (FR94).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

NO_ID_REUSE = {"sqlite_autoincrement": True}


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.Text))
    op.add_column("users", sa.Column("email_verified_at", sa.Text))
    # Emails are stored in lower case, so a plain unique index is enough; NULLs do not collide.
    op.create_index("idx_users_email", "users", ["email"], unique=True)
    op.execute("CREATE UNIQUE INDEX idx_users_username_nocase ON users (lower(username))")

    op.create_table(
        "user_tokens",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose", sa.Text, nullable=False),
        sa.Column("token_hash", sa.Text, nullable=False, unique=True),
        sa.Column("expires_at", sa.Text, nullable=False),
        sa.Column("used_at", sa.Text),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.CheckConstraint("purpose IN ('verify_email', 'reset_password')", name="user_tokens_purpose_check"),
        **NO_ID_REUSE,
    )
    op.create_index("idx_user_tokens_user", "user_tokens", ["user_id", "purpose"])

    op.create_table(
        "email_outbox",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("to_address", sa.Text, nullable=False),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text),
        sa.Column("next_attempt_at", sa.Text, nullable=False),
        sa.Column("claimed_at", sa.Text),
        sa.Column("created_at", sa.Text, nullable=False),
        sa.Column("sent_at", sa.Text),
        sa.CheckConstraint("status IN ('pending', 'sending', 'sent', 'failed')", name="email_outbox_status_check"),
        **NO_ID_REUSE,
    )
    op.create_index("idx_email_outbox_due", "email_outbox", ["status", "next_attempt_at"])

    op.create_table(
        "rate_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("created_at", sa.Text, nullable=False),
        **NO_ID_REUSE,
    )
    op.create_index("idx_rate_events_lookup", "rate_events", ["kind", "key", "created_at"])


def downgrade() -> None:
    op.drop_table("rate_events")
    op.drop_table("email_outbox")
    op.drop_table("user_tokens")
    op.drop_index("idx_users_username_nocase", "users")
    op.drop_index("idx_users_email", "users")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("email_verified_at")
        batch.drop_column("email")
