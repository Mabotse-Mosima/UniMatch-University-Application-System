"""Add school registry and auditable first SchoolAdmin bootstrap."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_school_administration"
down_revision = "0008_learner_document_storage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "schools",
        sa.Column("school_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("official_name", sa.String(255), nullable=False),
        sa.Column("emis_number", sa.String(32), nullable=True),
        sa.Column("province", sa.String(100), nullable=False, server_default=""),
        sa.Column("district", sa.String(150), nullable=False, server_default=""),
        sa.Column("contact_email", sa.String(254), nullable=True),
        sa.Column("contact_phone", sa.String(40), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column(
            "creator_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.account_id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('PendingVerification', 'Active', 'Suspended', 'NeedsReview')",
            name="ck_schools_status",
        ),
    )
    op.create_index(
        "uq_schools_emis_number",
        "schools",
        ["emis_number"],
        unique=True,
        postgresql_where=sa.text("emis_number IS NOT NULL"),
    )
    op.create_index(
        "uq_schools_official_name_ci",
        "schools",
        [sa.text("lower(official_name)")],
        unique=True,
    )
    op.create_index("ix_schools_status", "schools", ["status"])

    # Preserve existing school UUIDs, but do not invent official school identity.
    # The generated names and NeedsReview status require an administrator to verify
    # and replace them before they can be assigned to a new SchoolAdmin.
    op.execute(
        sa.text(
            """
            INSERT INTO schools
                (school_id, official_name, province, district, status, creator_id,
                 created_at, updated_at)
            SELECT ids.school_id,
                   'Unverified legacy school ' || ids.school_id::text,
                   '', '', 'NeedsReview', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM (
                SELECT school_id FROM accounts WHERE school_id IS NOT NULL
                UNION SELECT school_id FROM learners WHERE school_id IS NOT NULL
                UNION SELECT school_id FROM guidance_sessions WHERE school_id IS NOT NULL
                UNION SELECT school_id FROM audit_log_entries WHERE school_id IS NOT NULL
                UNION SELECT school_id FROM rag_conversations WHERE school_id IS NOT NULL
                UNION SELECT school_id FROM learner_documents WHERE school_id IS NOT NULL
            ) AS ids
            ON CONFLICT (school_id) DO NOTHING
            """
        )
    )

    # Additive constraints only after the legacy UUID backfill. No existing row is
    # reassigned or deleted; any omitted legacy reference makes the migration fail.
    op.create_foreign_key(
        "fk_accounts_school_id_schools", "accounts", "schools",
        ["school_id"], ["school_id"], ondelete="RESTRICT",
    )
    for table in (
        "learners", "guidance_sessions", "audit_log_entries",
        "rag_conversations", "learner_documents",
    ):
        op.create_foreign_key(
            f"fk_{table}_school_id_schools", table, "schools",
            ["school_id"], ["school_id"], ondelete="RESTRICT",
        )

    op.create_table(
        "school_admin_bootstrap_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "school_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("schools.school_id", ondelete="RESTRICT"),
            nullable=False, unique=True,
        ),
        sa.Column(
            "target_account_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.account_id", ondelete="RESTRICT"),
            nullable=False, unique=True,
        ),
        sa.Column(
            "actor_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.account_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("evidence_reference", sa.Text(), nullable=False),
        sa.Column("verification_evidence_reference", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_school_admin_bootstrap_events_school_id",
        "school_admin_bootstrap_events", ["school_id"],
    )
    op.create_table(
        "account_invitations",
        sa.Column("invitation_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.account_id", ondelete="CASCADE"),
            nullable=False, unique=True,
        ),
        sa.Column("token_digest", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "created_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.account_id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_account_invitations_account_id", "account_invitations", ["account_id"])


def downgrade() -> None:
    connection = op.get_bind()
    invitations = connection.execute(sa.text("SELECT COUNT(*) FROM account_invitations")).scalar_one()
    events = connection.execute(
        sa.text("SELECT COUNT(*) FROM school_admin_bootstrap_events")
    ).scalar_one()
    schools = connection.execute(sa.text("SELECT COUNT(*) FROM schools")).scalar_one()
    if invitations or events or schools:
        raise RuntimeError(
            "Downgrade refused: school registry or bootstrap records exist. "
            "Use a forward migration to preserve school identity and audit history."
        )
    op.drop_index(
        "ix_school_admin_bootstrap_events_school_id",
        table_name="school_admin_bootstrap_events",
    )
    op.drop_table("school_admin_bootstrap_events")
    for table in (
        "learner_documents", "rag_conversations", "audit_log_entries",
        "guidance_sessions", "learners", "accounts",
    ):
        op.drop_constraint(f"fk_{table}_school_id_schools", table, type_="foreignkey")
    op.drop_index("ix_schools_status", table_name="schools")
    op.drop_index("uq_schools_official_name_ci", table_name="schools")
    op.drop_index("uq_schools_emis_number", table_name="schools")
    op.drop_table("schools")
    op.drop_index("ix_account_invitations_account_id", table_name="account_invitations")
    op.drop_table("account_invitations")
