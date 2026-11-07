"""Allow learners to be created before a counsellor is assigned.

Revision ID: 0003_optional_counselor
Revises: 0002_auth_tables
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_optional_counselor"
down_revision = "0002_auth_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "learners",
        "counselor_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )


def downgrade() -> None:
    connection = op.get_bind()
    unassigned_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM learners WHERE counselor_id IS NULL")
    ).scalar_one()
    if unassigned_count:
        raise RuntimeError(
            "Downgrade refused: unassigned learners exist. Assign valid counsellors "
            "through an approved staff workflow before making counselor_id required."
        )

    op.alter_column(
        "learners",
        "counselor_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
