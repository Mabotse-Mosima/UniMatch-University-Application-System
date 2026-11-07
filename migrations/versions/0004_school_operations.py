"""Add persistent school guidance, notification, and audit records.

Revision ID: 0004_school_operations
Revises: 0003_optional_counselor
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_school_operations"
down_revision = "0003_optional_counselor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guidance_sessions",
        sa.Column("guidance_session_id", sa.Uuid(), nullable=False),
        sa.Column("learner_id", sa.Uuid(), nullable=False),
        sa.Column("school_id", sa.Uuid(), nullable=False),
        sa.Column("responsible_staff_id", sa.Uuid(), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("purpose", sa.String(length=255), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["learner_id"], ["learners.learner_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["responsible_staff_id"], ["accounts.account_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("guidance_session_id"),
        sa.CheckConstraint(
            "status IN ('Scheduled','Completed','Cancelled')",
            name="ck_guidance_sessions_status",
        ),
    )
    op.create_index(
        "ix_guidance_sessions_learner_id", "guidance_sessions", ["learner_id"]
    )
    op.create_index(
        "ix_guidance_sessions_school_id", "guidance_sessions", ["school_id"]
    )

    op.create_table(
        "notifications",
        sa.Column("notification_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column("notification_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("event_key", sa.String(length=255)),
        sa.ForeignKeyConstraint(
            ["recipient_id"], ["accounts.account_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("notification_id"),
        sa.UniqueConstraint("event_key", name="uq_notifications_event_key"),
        sa.CheckConstraint(
            "status IN ('Unread','Read','Sent','Failed')",
            name="ck_notifications_status",
        ),
    )
    op.create_index("ix_notifications_recipient_id", "notifications", ["recipient_id"])

    op.create_table(
        "audit_log_entries",
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("target_type", sa.String(length=80), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("school_id", sa.Uuid()),
        sa.Column("university_id", sa.Uuid()),
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["accounts.account_id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("entry_id"),
    )
    op.create_index("ix_audit_log_entries_actor_id", "audit_log_entries", ["actor_id"])
    op.create_index("ix_audit_log_entries_target_id", "audit_log_entries", ["target_id"])
    op.create_index("ix_audit_log_entries_school_id", "audit_log_entries", ["school_id"])
    op.create_index(
        "ix_audit_log_entries_university_id", "audit_log_entries", ["university_id"]
    )
    op.create_index("ix_audit_log_entries_timestamp", "audit_log_entries", ["timestamp"])


def downgrade() -> None:
    connection = op.get_bind()
    for table in ("audit_log_entries", "notifications", "guidance_sessions"):
        count = connection.execute(
            sa.text(f'SELECT COUNT(*) FROM "{table}"')
        ).scalar_one()
        if count:
            raise RuntimeError(
                f"Downgrade refused: {count} row(s) exist in '{table}'. "
                "Preserve operational and audit history with a forward migration."
            )

    op.drop_index("ix_audit_log_entries_timestamp", table_name="audit_log_entries")
    op.drop_index("ix_audit_log_entries_university_id", table_name="audit_log_entries")
    op.drop_index("ix_audit_log_entries_school_id", table_name="audit_log_entries")
    op.drop_index("ix_audit_log_entries_target_id", table_name="audit_log_entries")
    op.drop_index("ix_audit_log_entries_actor_id", table_name="audit_log_entries")
    op.drop_table("audit_log_entries")
    op.drop_index("ix_notifications_recipient_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_guidance_sessions_school_id", table_name="guidance_sessions")
    op.drop_index("ix_guidance_sessions_learner_id", table_name="guidance_sessions")
    op.drop_table("guidance_sessions")
