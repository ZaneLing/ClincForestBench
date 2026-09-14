"""Add prototype physician accounts and login sessions."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("physician_accounts"):
        op.create_table(
            "physician_accounts",
            sa.Column("username", sa.String(), primary_key=True),
            sa.Column("password_plaintext", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if not inspector.has_table("auth_sessions"):
        op.create_table(
            "auth_sessions",
            sa.Column("token", sa.String(), primary_key=True),
            sa.Column(
                "username",
                sa.String(),
                sa.ForeignKey("physician_accounts.username"),
                nullable=False,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_auth_sessions_username", "auth_sessions", ["username"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("auth_sessions"):
        op.drop_index("ix_auth_sessions_username", table_name="auth_sessions")
        op.drop_table("auth_sessions")
    if inspector.has_table("physician_accounts"):
        op.drop_table("physician_accounts")
