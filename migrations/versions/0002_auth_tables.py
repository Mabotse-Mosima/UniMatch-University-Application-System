"""Add authentication tables: accounts, account_sessions, verification_records.

Revision ID: 0002_auth_tables
Revises: 0001_initial
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_auth_tables"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # accounts — must be created before tables that reference it via FK.
    op.create_table(
        "accounts",
        sa.Column("account_id",      sa.Uuid(),              nullable=False),
        sa.Column("email",           sa.String(length=254),  nullable=False),
        sa.Column("password_hash",   sa.String(length=512),  nullable=False),
        sa.Column("role",            sa.String(length=30),   nullable=False),
        sa.Column("account_state",   sa.String(length=20),   nullable=False, server_default="Pending"),
        sa.Column("failed_attempts", sa.Integer(),           nullable=False, server_default="0"),
        sa.Column("locked_until",    sa.DateTime(timezone=True)),
        sa.Column("school_id",       sa.Uuid()),
        sa.Column("university_id",   sa.Uuid()),
        sa.Column("creator_id",      sa.Uuid(),
                  sa.ForeignKey("accounts.account_id", ondelete="RESTRICT")),
        sa.Column("created_at",      sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at",      sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "account_state IN ('Pending','Active','Suspended')",
            name="ck_accounts_state",
        ),
        sa.PrimaryKeyConstraint("account_id"),
    )
    # Case-insensitive email uniqueness — never NOW() in predicate (mutable).
    op.create_index(
        "uq_accounts_email_ci",
        "accounts",
        [sa.text("LOWER(email)")],
        unique=True,
    )
    # At most one SystemAdmin.
    op.create_index(
        "uq_accounts_single_system_admin",
        "accounts",
        ["role"],
        unique=True,
        postgresql_where=sa.text("role = 'SystemAdmin'"),
    )
    op.create_index("ix_accounts_role",          "accounts", ["role"])
    op.create_index("ix_accounts_account_state", "accounts", ["account_state"])

    # account_sessions
    op.create_table(
        "account_sessions",
        sa.Column("session_id",   sa.Uuid(),                nullable=False),
        sa.Column("account_id",   sa.Uuid(),                nullable=False),
        sa.Column("token_digest", sa.String(length=64),     nullable=False),
        sa.Column("csrf_token",   sa.String(length=64),     nullable=False),
        sa.Column("created_at",   sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at",   sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at",   sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.account_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("session_id"),
        sa.UniqueConstraint("token_digest", name="uq_account_sessions_digest"),
    )
    op.create_index("ix_account_sessions_account_id", "account_sessions", ["account_id"])
    op.create_index("ix_account_sessions_expires_at", "account_sessions", ["expires_at"])
    # No partial index on token_digest: the UNIQUE constraint creates the index,
    # and find_by_token_digest queries do not filter by revoked_at.

    # verification_records
    op.create_table(
        "verification_records",
        sa.Column("record_id",            sa.Uuid(),    nullable=False),
        sa.Column("subject_account_id",   sa.Uuid(),    nullable=False),
        sa.Column("verifier_account_id",  sa.Uuid(),    nullable=False),
        sa.Column("subject_role",         sa.String(length=30), nullable=False),
        sa.Column("evidence_reference",   sa.Text(),    nullable=False),
        sa.Column("school_scope",         postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default=sa.text("'[]'")),
        sa.Column("university_id",        sa.Uuid()),
        sa.Column("created_at",           sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome",              sa.String(length=20), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('Verified','Rejected')",
            name="ck_verification_outcome",
        ),
        sa.ForeignKeyConstraint(
            ["subject_account_id"],  ["accounts.account_id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["verifier_account_id"], ["accounts.account_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("record_id"),
    )
    op.create_index(
        "ix_verification_records_subject",
        "verification_records",
        ["subject_account_id", "created_at", "record_id"],
    )
    op.create_index(
        "ix_verification_records_verifier",
        "verification_records",
        ["verifier_account_id"],
    )


def downgrade() -> None:
    """Refuse to drop authentication tables if any contain data."""
    conn = op.get_bind()
    checks = [
        ("accounts",             "authentication accounts"),
        ("account_sessions",     "session records"),
        ("verification_records", "verification and audit records"),
    ]
    for table, description in checks:
        count = conn.execute(
            sa.text(f'SELECT COUNT(*) FROM "{table}"')
        ).scalar_one()
        if count > 0:
            raise RuntimeError(
                f"Downgrade refused: {count} row(s) exist in '{table}' "
                f"({description}). Dropping authentication tables would destroy "
                "data irreversibly. Restore from backup or apply a forward "
                "corrective migration instead."
            )
    # All three empty — safe to drop (reverse of creation order).
    op.drop_index("ix_verification_records_verifier", table_name="verification_records")
    op.drop_index("ix_verification_records_subject",  table_name="verification_records")
    op.drop_table("verification_records")

    op.drop_index("ix_account_sessions_expires_at",  table_name="account_sessions")
    op.drop_index("ix_account_sessions_account_id",  table_name="account_sessions")
    op.drop_table("account_sessions")

    op.drop_index("ix_accounts_account_state",             table_name="accounts")
    op.drop_index("ix_accounts_role",                      table_name="accounts")
    op.drop_index("uq_accounts_single_system_admin",       table_name="accounts")
    op.drop_index("uq_accounts_email_ci",                  table_name="accounts")
    op.drop_table("accounts")
