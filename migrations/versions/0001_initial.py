"""Create the initial active API persistence schema.

Revision ID: 0001_initial
Revises:
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learners",
        sa.Column("learner_id", sa.Uuid(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("school_id_number", sa.String(length=100), nullable=False),
        sa.Column("grade", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("counselor_id", sa.Uuid(), nullable=False),
        sa.Column("school_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("learner_id"),
    )
    op.create_index("ix_learners_counselor_id", "learners", ["counselor_id"])
    op.create_index("ix_learners_school_id", "learners", ["school_id"])

    op.create_table(
        "university_programmes",
        sa.Column("programme_id", sa.Uuid(), nullable=False),
        sa.Column("university_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("faculty", sa.String(length=255), nullable=False),
        sa.Column("minimum_aps", sa.Integer(), nullable=False),
        sa.Column("application_deadline", sa.Date(), nullable=False),
        sa.Column("application_fee", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("required_documents", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("published_by", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("required_subjects", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("programme_id"),
    )
    op.create_index(
        "ix_university_programmes_university_id",
        "university_programmes",
        ["university_id"],
    )
    op.create_index(
        "ix_university_programmes_status",
        "university_programmes",
        ["status"],
    )

    op.create_table(
        "scoring_rules",
        sa.Column("university_id", sa.Uuid(), nullable=False),
        sa.Column("band_thresholds", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("subject_count", sa.Integer(), nullable=False),
        sa.Column("excluded_subjects", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("subject_weightings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("university_id"),
    )

    op.create_table(
        "marks",
        sa.Column("mark_id", sa.Uuid(), nullable=False),
        sa.Column("learner_id", sa.Uuid(), nullable=False),
        sa.Column("subject_name", sa.String(length=255), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("exam_type", sa.String(length=100), nullable=False),
        sa.Column("academic_year", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["learner_id"], ["learners.learner_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("mark_id"),
    )
    op.create_index("ix_marks_learner_id", "marks", ["learner_id"])

    op.create_table(
        "applications",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("learner_id", sa.Uuid(), nullable=False),
        sa.Column("programme_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("payment_reference", sa.String(length=255), nullable=False),
        sa.Column("fee_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("submission_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledgement_reference", sa.String(length=255), nullable=False),
        sa.Column("programme_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("application_id"),
    )
    op.create_index("ix_applications_learner_id", "applications", ["learner_id"])
    op.create_index("ix_applications_programme_id", "applications", ["programme_id"])
    op.create_index("ix_applications_status", "applications", ["status"])

    op.create_table(
        "application_status_history",
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("previous_status", sa.String(length=50), nullable=False),
        sa.Column("new_status", sa.String(length=50), nullable=False),
        sa.Column("changed_by", sa.Uuid(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.application_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("entry_id"),
    )
    op.create_index(
        "ix_application_status_history_application_id",
        "application_status_history",
        ["application_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_application_status_history_application_id",
        table_name="application_status_history",
    )
    op.drop_table("application_status_history")
    op.drop_index("ix_applications_status", table_name="applications")
    op.drop_index("ix_applications_programme_id", table_name="applications")
    op.drop_index("ix_applications_learner_id", table_name="applications")
    op.drop_table("applications")
    op.drop_index("ix_marks_learner_id", table_name="marks")
    op.drop_table("marks")
    op.drop_table("scoring_rules")
    op.drop_index("ix_university_programmes_status", table_name="university_programmes")
    op.drop_index(
        "ix_university_programmes_university_id",
        table_name="university_programmes",
    )
    op.drop_table("university_programmes")
    op.drop_index("ix_learners_school_id", table_name="learners")
    op.drop_index("ix_learners_counselor_id", table_name="learners")
    op.drop_table("learners")
