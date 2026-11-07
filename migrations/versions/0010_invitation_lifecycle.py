"""Preserve invitation history and record explicit lifecycle states.

Revision ID: 0010_invitation_lifecycle
Revises: 0009_school_administration

Existing rows are backfilled from consumed_at, expiration, and matching prior
revocation audit events. A prior revocation whose audit event is absent cannot
be distinguished from natural expiry and is backfilled as Expired.
"""

from alembic import op
import sqlalchemy as sa

revision = "0010_invitation_lifecycle"
down_revision = "0009_school_administration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "account_invitations",
        sa.Column("status", sa.String(20), nullable=False, server_default="Pending"),
    )
    op.create_check_constraint(
        "ck_account_invitations_status",
        "account_invitations",
        "status IN ('Pending', 'Accepted', 'Expired', 'Revoked')",
    )
    op.execute(
        sa.text(
            "UPDATE account_invitations SET status = 'Accepted' "
            "WHERE consumed_at IS NOT NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE account_invitations SET status = 'Revoked' "
            "WHERE consumed_at IS NULL AND EXISTS ("
            "SELECT 1 FROM audit_log_entries audit "
            "WHERE audit.target_type = 'Account' "
            "AND audit.target_id = account_invitations.account_id "
            "AND audit.action = 'SchoolAdminInvitationRevoked'"
            ")"
        )
    )
    op.execute(
        sa.text(
            "UPDATE account_invitations SET status = 'Expired' "
            "WHERE status = 'Pending' AND consumed_at IS NULL "
            "AND expires_at <= CURRENT_TIMESTAMP"
        )
    )
    # 0009 made account_id unique, which prevented preserving old invitations
    # when issuing a replacement. Keep the account index and remove only the
    # uniqueness constraint; token digests remain unique.
    op.drop_constraint(
        "account_invitations_account_id_key",
        "account_invitations",
        type_="unique",
    )


def downgrade() -> None:
    connection = op.get_bind()
    revoked = connection.execute(
        sa.text("SELECT COUNT(*) FROM account_invitations WHERE status = 'Revoked'")
    ).scalar_one()
    duplicate_accounts = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM ("
            "SELECT account_id FROM account_invitations GROUP BY account_id HAVING COUNT(*) > 1"
            ") AS histories"
        )
    ).scalar_one()
    if revoked or duplicate_accounts:
        raise RuntimeError(
            "Downgrade refused: revoked or replacement invitation history exists. "
            "Use a forward migration to preserve invitation lifecycle history."
        )
    op.create_unique_constraint(
        "account_invitations_account_id_key", "account_invitations", ["account_id"]
    )
    op.drop_constraint(
        "ck_account_invitations_status", "account_invitations", type_="check"
    )
    op.drop_column("account_invitations", "status")
