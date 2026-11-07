"""Add institution directory, explicit university scopes and reviewed import drafts.

Revision ID: 0011_university_directory
Revises: 0010_invitation_lifecycle

This is an additive migration. Existing UUID scopes used by programmes and RAG
documents are preserved as unverified legacy directory rows. No legacy UUID is
guessed to belong to a named institution.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID, uuid5

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0011_university_directory"
down_revision = "0010_invitation_lifecycle"
branch_labels = None
depends_on = None

_NAMESPACE = UUID("8aaae526-4c7a-5b14-8b19-a5746e98f880")
_PUBLIC = (
    ("Cape Peninsula University of Technology", "CPUT"),
    ("Central University of Technology, Free State", "CUT"),
    ("Durban University of Technology", "DUT"),
    ("Mangosuthu University of Technology", "MUT"),
    ("Nelson Mandela University", "NMU"),
    ("North-West University", "NWU"),
    ("Rhodes University", "RU"),
    ("Sefako Makgatho Health Sciences University", "SMU"),
    ("Sol Plaatje University", "SPU"),
    ("Stellenbosch University", "SU"),
    ("Tshwane University of Technology", "TUT"),
    ("University of Cape Town", "UCT"),
    ("University of Fort Hare", "UFH"),
    ("University of Johannesburg", "UJ"),
    ("University of KwaZulu-Natal", "UKZN"),
    ("University of Limpopo", "UL"),
    ("University of Mpumalanga", "UMP"),
    ("University of Pretoria", "UP"),
    ("University of South Africa", "UNISA"),
    ("University of the Free State", "UFS"),
    ("University of the Western Cape", "UWC"),
    ("University of the Witwatersrand", "Wits"),
    ("University of Zululand", "UNIZULU"),
    ("University of Venda", "UNIVEN"),
    ("Vaal University of Technology", "VUT"),
    ("Walter Sisulu University", "WSU"),
)
_DHET_PUBLIC_URL = "https://www.dhet.gov.za/SitePages/UniversitiesinSA.aspx"


def upgrade() -> None:
    op.create_table(
        "university_institutions",
        sa.Column("university_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("abbreviation", sa.String(32), nullable=False),
        sa.Column("sector", sa.String(20), nullable=False),
        sa.Column("dhet_reference", sa.String(100)),
        sa.Column("website", sa.String(500)),
        sa.Column("status", sa.String(20), nullable=False, server_default="Active"),
        sa.Column("catalog_source", sa.String(500), nullable=False),
        sa.Column("source_checked_on", sa.Date()),
        sa.Column("verification_reference", sa.Text()),
        sa.Column("verified_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.account_id", ondelete="SET NULL")),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sector IN ('Public', 'Private', 'Legacy')", name="ck_university_institutions_sector"),
        sa.CheckConstraint("status IN ('Active', 'Inactive', 'Unverified')", name="ck_university_institutions_status"),
    )
    op.create_index(
        "uq_university_institutions_name_ci",
        "university_institutions",
        [sa.text("lower(name)")],
        unique=True,
    )
    op.create_unique_constraint(
        "uq_university_institutions_abbreviation", "university_institutions", ["abbreviation"]
    )

    op.create_table(
        "account_university_scopes",
        sa.Column(
            "account_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.account_id", ondelete="CASCADE"), primary_key=True,
        ),
        sa.Column(
            "university_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("university_institutions.university_id", ondelete="RESTRICT"), primary_key=True,
        ),
        sa.Column(
            "granted_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.account_id", ondelete="RESTRICT"), nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_account_university_scopes_university", "account_university_scopes", ["university_id"])

    op.create_table(
        "programme_import_drafts",
        sa.Column("draft_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "university_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("university_institutions.university_id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column(
            "source_document_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rag_documents.document_id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("faculty", sa.String(255)),
        sa.Column("minimum_aps", sa.Integer()),
        sa.Column("application_deadline", sa.Date()),
        sa.Column("application_fee", sa.Numeric(12, 2)),
        sa.Column("required_documents", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("required_subjects", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("source_evidence", sa.Text(), nullable=False),
        sa.Column("extraction_notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="NeedsReview"),
        sa.Column(
            "reviewed_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.account_id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_document_id", "name", "minimum_aps", name="uq_programme_import_drafts_source_candidate"),
        sa.CheckConstraint("status IN ('NeedsReview', 'Approved', 'Rejected', 'Submitted')", name="ck_programme_import_drafts_status"),
        sa.CheckConstraint("minimum_aps IS NULL OR (minimum_aps >= 0 AND minimum_aps <= 42)", name="ck_programme_import_drafts_aps"),
    )
    op.create_index(
        "ix_programme_import_drafts_scope_status", "programme_import_drafts", ["university_id", "status"]
    )

    op.add_column("university_programmes", sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_university_programmes_source_document", "university_programmes", "rag_documents",
        ["source_document_id"], ["document_id"], ondelete="SET NULL",
    )
    op.add_column("university_programmes", sa.Column("source_draft_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_university_programmes_source_draft", "university_programmes", "programme_import_drafts",
        ["source_draft_id"], ["draft_id"], ondelete="SET NULL",
    )
    op.create_index("uq_university_programmes_source_draft", "university_programmes", ["source_draft_id"], unique=True, postgresql_where=sa.text("source_draft_id IS NOT NULL"))
    op.add_column("university_programmes", sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_university_programmes_reviewed_by", "university_programmes", "accounts",
        ["reviewed_by"], ["account_id"], ondelete="SET NULL",
    )
    op.add_column("university_programmes", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))

    connection = op.get_bind()
    now = datetime.now(timezone.utc)
    for name, abbreviation in _PUBLIC:
        connection.execute(
            sa.text(
                "INSERT INTO university_institutions "
                "(university_id, name, abbreviation, sector, status, catalog_source, source_checked_on, created_at, updated_at) "
                "VALUES (:id, :name, :code, 'Public', 'Active', :source, :checked, :now, :now) "
                "ON CONFLICT (university_id) DO NOTHING"
            ),
            {
                "id": uuid5(_NAMESPACE, abbreviation), "name": name, "code": abbreviation,
                "source": _DHET_PUBLIC_URL, "checked": date(2026, 11, 5), "now": now,
            },
        )

    # Preserve historic UUID scopes, but do not guess which official institution
    # a legacy UUID represents. A SystemAdmin can resolve these rows later.
    legacy_ids = connection.execute(sa.text(
        "SELECT university_id FROM accounts WHERE university_id IS NOT NULL "
        "UNION SELECT university_id FROM university_programmes "
        "UNION SELECT university_id FROM rag_documents "
        "UNION SELECT university_id FROM rag_logical_documents "
        "UNION SELECT university_id FROM scoring_rules"
    )).scalars().all()
    for university_id in legacy_ids:
        connection.execute(
            sa.text(
                "INSERT INTO university_institutions "
                "(university_id, name, abbreviation, sector, status, catalog_source, created_at, updated_at) "
                "VALUES (:id, :name, :code, 'Legacy', 'Unverified', 'Pre-0011 existing UUID scope', :now, :now) "
                "ON CONFLICT (university_id) DO NOTHING"
            ),
            {"id": university_id, "name": f"Legacy institution {str(university_id)[:8]}",
             "code": f"LEGACY-{str(university_id)[:8]}", "now": now},
        )
    connection.execute(sa.text(
        "INSERT INTO account_university_scopes (account_id, university_id, granted_by, created_at) "
        "SELECT account_id, university_id, creator_id, :now FROM accounts "
        "WHERE role = 'UniversityAdmissions' AND university_id IS NOT NULL "
        "ON CONFLICT (account_id, university_id) DO NOTHING"
    ), {"now": now})


def downgrade() -> None:
    connection = op.get_bind()
    draft_count = connection.execute(sa.text("SELECT COUNT(*) FROM programme_import_drafts")).scalar_one()
    scope_count = connection.execute(sa.text("SELECT COUNT(*) FROM account_university_scopes")).scalar_one()
    if draft_count or scope_count:
        raise RuntimeError(
            "Downgrade refused: university scopes or reviewed programme import history exists. "
            "Use a forward migration to preserve these records."
        )
    op.drop_constraint("fk_university_programmes_reviewed_by", "university_programmes", type_="foreignkey")
    op.drop_column("university_programmes", "reviewed_at")
    op.drop_column("university_programmes", "reviewed_by")
    op.drop_constraint("fk_university_programmes_source_draft", "university_programmes", type_="foreignkey")
    op.drop_index("uq_university_programmes_source_draft", table_name="university_programmes")
    op.drop_column("university_programmes", "source_draft_id")
    op.drop_constraint("fk_university_programmes_source_document", "university_programmes", type_="foreignkey")
    op.drop_column("university_programmes", "source_document_id")
    op.drop_index("ix_programme_import_drafts_scope_status", table_name="programme_import_drafts")
    op.drop_table("programme_import_drafts")
    op.drop_index("ix_account_university_scopes_university", table_name="account_university_scopes")
    op.drop_table("account_university_scopes")
    op.drop_constraint("uq_university_institutions_abbreviation", "university_institutions", type_="unique")
    op.drop_index("uq_university_institutions_name_ci", table_name="university_institutions")
    op.drop_table("university_institutions")
