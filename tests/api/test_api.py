"""
tests/api/test_api.py
======================
Integration tests for the UniMatch REST API.

Uses FastAPI's TestClient exercising all endpoints end-to-end through the full
stack: API → Service → In-Memory Repository.  All tests authenticate through
the real login flow (SchoolAdmin for learner/application ops, UniversityAdmin
for programme mutations).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from unimatch.api import create_app
from unimatch.auth import AuthPrincipal, hash_password
from unimatch.bootstrap import bootstrap_system_admin
from unimatch.entities import NSC_DEFAULT_SCORING_RULE, ScoringRule, UserAccount
from unimatch.enums import AccountStateEnum, RoleEnum
from unimatch.provisioning import AccountProvisioningService
from unimatch.repositories.inmemory import (
    InMemorySessionRepository,
    InMemoryScoringRuleRepository,
    InMemoryUserAccountRepository,
    InMemoryVerificationRecordRepository,
)
from unimatch.repositories.local_documents import LocalDocumentRepository


# ─────────────────────────────────────────────────────────────────────────────
# Shared test context
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TestContext:
    school_client: TestClient   # authenticated as SchoolAdmin
    uni_client: TestClient      # authenticated as UniversityAdmin
    doe_client: TestClient     # authenticated as DoEOfficial
    school_id: UUID
    university_id: UUID
    school_csrf: str
    uni_csrf: str


def _build_test_context(
    scoring_rule_repo=None,
    school_id: UUID | None = None,
    university_id: UUID | None = None,
    document_storage_dir: Path | None = None,
) -> TestContext:
    """Build a fully authenticated test context with shared in-memory repos."""
    school_id = school_id or uuid4()
    university_id = university_id or uuid4()

    account_repo = InMemoryUserAccountRepository()
    session_repo = InMemorySessionRepository()
    verification_repo = InMemoryVerificationRecordRepository()

    admin1 = bootstrap_system_admin(
        account_repo, _email="admin1@tc.test", _password="Admin1Pass!"
    )
    admin2 = UserAccount(
        user_id=uuid4(),
        email="admin2@tc.test",
        password_hash=hash_password("Admin2Pass!"),
        role=RoleEnum.SystemAdmin,
        account_state=AccountStateEnum.Active,
    )
    account_repo.save(admin2)

    svc = AccountProvisioningService(
        account_repo=account_repo, verification_repo=verification_repo
    )
    p1 = AuthPrincipal(
        account_id=admin1.user_id,
        role=RoleEnum.SystemAdmin,
        account_state=AccountStateEnum.Active,
    )
    p2 = AuthPrincipal(
        account_id=admin2.user_id,
        role=RoleEnum.SystemAdmin,
        account_state=AccountStateEnum.Active,
    )

    sa = svc.provision_account(
        p1, "sa@tc.test", "SAPass1!", RoleEnum.SchoolAdmin, school_id=school_id
    )
    svc.record_verification(
        p1, sa.user_id, "REF-SA-001", school_scope=[school_id]
    )
    svc.activate_account(p2, sa.user_id)

    ua = svc.provision_account(
        p1, "ua@tc.test", "UAPass1!", RoleEnum.UniversityAdmissions,
        university_id=university_id,
    )
    svc.record_verification(p1, ua.user_id, "REF-UA-001", university_id=university_id)
    svc.activate_account(p2, ua.user_id)

    doe = UserAccount(
        user_id=uuid4(),
        email="doe@tc.test",
        password_hash=hash_password("DoEPass1!"),
        role=RoleEnum.DoEOfficial,
        account_state=AccountStateEnum.Active,
    )
    account_repo.save(doe)

    app = create_app(
        scoring_rule_repo=scoring_rule_repo,
        account_repo=account_repo,
        session_repo=session_repo,
        verification_repo=verification_repo,
        document_storage_dir=document_storage_dir,
    )
    school_client = TestClient(app, raise_server_exceptions=False)
    uni_client = TestClient(app, raise_server_exceptions=False)
    doe_client = TestClient(app, raise_server_exceptions=False)

    school_client.post(
        "/api/auth/login", json={"email": "sa@tc.test", "password": "SAPass1!"}
    )
    school_csrf = school_client.get("/api/auth/csrf").json()["csrf_token"]

    uni_client.post(
        "/api/auth/login", json={"email": "ua@tc.test", "password": "UAPass1!"}
    )
    uni_csrf = uni_client.get("/api/auth/csrf").json()["csrf_token"]

    doe_client.post(
        "/api/auth/login", json={"email": "doe@tc.test", "password": "DoEPass1!"}
    )

    return TestContext(
        school_client=school_client,
        uni_client=uni_client,
        doe_client=doe_client,
        school_id=school_id,
        university_id=university_id,
        school_csrf=school_csrf,
        uni_csrf=uni_csrf,
    )


@pytest.fixture(scope="module")
def tc() -> TestContext:
    """Module-scoped shared test context."""
    return _build_test_context()


# ── Legacy constants kept for any remaining assertions ────────────────────────
COUNSELOR_ID = str(uuid4())
SCHOOL_ID = str(uuid4())
UNIVERSITY_ID = str(uuid4())
PUBLISHER_ID = str(uuid4())
ACTOR_ID = str(uuid4())
FAR_FUTURE = "2099-12-31"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _create_learner(
    tc: TestContext,
    full_name: str = "Thabo Nkosi",
    school_id_number: str = "SCH-001",
) -> dict:
    resp = tc.school_client.post(
        "/api/learners",
        json={
            "full_name": full_name,
            "school_id_number": school_id_number,
            "grade": 12,
            "counselor_id": str(uuid4()),
            "school_id": str(tc.school_id),
        },
        headers={"X-CSRF-Token": tc.school_csrf},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_programme(
    tc: TestContext,
    deadline: str = FAR_FUTURE,
    aps: int = 28,
    required_subjects: dict | None = None,
) -> dict:
    body = {
        "university_id": str(tc.university_id),
        "name": "BSc Computer Science",
        "faculty": "Science",
        "minimum_aps": aps,
        "application_deadline": deadline,
        "application_fee": "200.00",
        "required_documents": ["ID", "Matric Certificate"],
        "published_by": str(uuid4()),
    }
    if required_subjects is not None:
        body["required_subjects"] = required_subjects
    resp = tc.uni_client.post(
        "/api/programmes", json=body, headers={"X-CSRF-Token": tc.uni_csrf}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _publish_programme(tc: TestContext, pid: str) -> dict:
    resp = tc.uni_client.post(
        f"/api/programmes/{pid}/publish",
        headers={"X-CSRF-Token": tc.uni_csrf},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _create_and_publish_programme(
    tc: TestContext,
    aps: int = 28,
    required_subjects: dict | None = None,
) -> dict:
    prog = _create_programme(tc, aps=aps, required_subjects=required_subjects)
    return _publish_programme(tc, prog["programme_id"])


def _add_marks_via_api(tc: TestContext, learner_id: str, score: int = 90) -> None:
    subjects = [
        "Mathematics", "English", "Life Sciences",
        "Physical Sciences", "History", "Geography",
    ]
    for subj in subjects:
        resp = tc.school_client.post(
            f"/api/learners/{learner_id}/marks",
            json={
                "subject_name": subj, "score": score,
                "exam_type": "NSC", "academic_year": 2024,
            },
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert resp.status_code == 201, resp.text


def test_learner_documents_are_stored_reviewed_and_block_paymentless_submission(
    tmp_path: Path,
) -> None:
    tc = _build_test_context(document_storage_dir=tmp_path)
    learner = _create_learner(tc)
    _add_marks_via_api(tc, learner["learner_id"])
    programme = _create_and_publish_programme(tc)
    application_response = tc.school_client.post(
        "/api/applications",
        json={
            "learner_id": learner["learner_id"],
            "programme_id": programme["programme_id"],
            "fee_amount": "200.00",
        },
        headers={"X-CSRF-Token": tc.school_csrf},
    )
    assert application_response.status_code == 201, application_response.text
    application_id = application_response.json()["application_id"]

    pdf_content = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF"
    uploaded_documents = []
    for document_type, filename in (
        ("ID", "identity.pdf"),
        ("Matric Certificate", "results.pdf"),
    ):
        response = tc.school_client.post(
            f"/api/learners/{learner['learner_id']}/documents",
            data={
                "document_type": document_type,
                "application_id": application_id,
            },
            files={"file": (filename, pdf_content, "application/pdf")},
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert response.status_code == 201, response.text
        document = response.json()
        assert document["status"] == "PendingReview"
        assert document["virus_scan_status"] == "NotScanned"
        assert "storage_path" not in document
        uploaded_documents.append(document)

    for document in uploaded_documents:
        response = tc.school_client.put(
            f"/api/documents/{document['document_id']}/review",
            json={"decision": "Verified", "note": "Original checked by school staff."},
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert response.status_code == 200, response.text
        assert response.json()["reviewed_by"]
        assert response.json()["reviewed_at"]

        downloaded = tc.school_client.get(document["download_url"])
        assert downloaded.status_code == 200
        assert downloaded.content == pdf_content

    package_ready = tc.school_client.put(
        f"/api/applications/{application_id}/status",
        json={"new_status": "PackageReady", "note": "Required documents verified."},
        headers={"X-CSRF-Token": tc.school_csrf},
    )
    assert package_ready.status_code == 409
    assert "confirmed payment" in package_ready.json()["detail"]

    submit = tc.school_client.post(
        f"/api/applications/{application_id}/submit",
        headers={"X-CSRF-Token": tc.school_csrf},
    )
    assert submit.status_code == 409
    current_application = tc.school_client.get(
        f"/api/applications/{application_id}"
    ).json()
    assert current_application["status"] == "Draft"
    assert current_application["submission_ready"] is False
    persisted_documents = LocalDocumentRepository(tmp_path).find_by_learner(
        UUID(learner["learner_id"])
    )
    assert len(persisted_documents) == 2
    assert {document.status for document in persisted_documents} == {"Verified"}


def test_learner_document_upload_rejects_mismatched_file_content(tmp_path: Path) -> None:
    tc = _build_test_context(document_storage_dir=tmp_path)
    learner = _create_learner(tc)
    response = tc.school_client.post(
        f"/api/learners/{learner['learner_id']}/documents",
        data={"document_type": "ID"},
        files={"file": ("not-a-pdf.pdf", b"not a PDF", "application/pdf")},
        headers={"X-CSRF-Token": tc.school_csrf},
    )
    assert response.status_code == 422
    assert list(tmp_path.rglob("*")) == []


def _create_eligible_learner(tc: TestContext) -> dict:
    learner = _create_learner(tc)
    _add_marks_via_api(tc, learner["learner_id"])
    return learner


def _create_application(tc: TestContext, learner_id: str, programme_id: str) -> dict:
    resp = tc.school_client.post(
        "/api/applications",
        json={"learner_id": learner_id, "programme_id": programme_id, "fee_amount": "200.00"},
        headers={"X-CSRF-Token": tc.school_csrf},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _school_admin_id(tc: TestContext) -> str:
    return tc.school_client.get("/api/auth/me").json()["account_id"]


# ─────────────────────────────────────────────────────────────────────────────
# Health check (public)
# ─────────────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_check(self, tc: TestContext):
        resp = tc.school_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ─────────────────────────────────────────────────────────────────────────────
# Learner endpoints
# ─────────────────────────────────────────────────────────────────────────────

class TestLearnerEndpoints:

    def test_create_learner(self, tc: TestContext):
        learner = _create_learner(tc)
        assert learner["full_name"] == "Thabo Nkosi"
        assert learner["grade"] == 12
        assert "learner_id" in learner
        assert learner["school_id"] == str(tc.school_id)

    def test_create_learner_without_counsellor(self, tc: TestContext):
        response = tc.school_client.post(
            "/api/learners",
            json={
                "full_name": "Unassigned Learner",
                "school_id_number": "SCH-NO-COUNSELLOR",
                "grade": 11,
            },
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert response.status_code == 201, response.text
        assert response.json()["counselor_id"] is None

    def test_get_learner(self, tc: TestContext):
        learner = _create_learner(tc)
        resp = tc.school_client.get(f"/api/learners/{learner['learner_id']}")
        assert resp.status_code == 200
        assert resp.json()["learner_id"] == learner["learner_id"]

    def test_get_nonexistent_learner_404(self, tc: TestContext):
        resp = tc.school_client.get(f"/api/learners/{uuid4()}")
        assert resp.status_code == 404

    def test_list_learners(self, tc: TestContext):
        _create_learner(tc)
        resp = tc.school_client.get("/api/learners")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert len(resp.json()) >= 1

    def test_update_learner(self, tc: TestContext):
        learner = _create_learner(tc)
        resp = tc.school_client.put(
            f"/api/learners/{learner['learner_id']}",
            json={"full_name": "Sipho Dlamini"},
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert resp.status_code == 200
        assert resp.json()["full_name"] == "Sipho Dlamini"

    def test_delete_learner(self, tc: TestContext):
        learner = _create_learner(tc)
        resp = tc.school_client.delete(
            f"/api/learners/{learner['learner_id']}",
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert resp.status_code == 204
        assert tc.school_client.get(f"/api/learners/{learner['learner_id']}").status_code == 404

    def test_add_mark(self, tc: TestContext):
        learner = _create_learner(tc)
        resp = tc.school_client.post(
            f"/api/learners/{learner['learner_id']}/marks",
            json={"subject_name": "Mathematics", "score": 80, "exam_type": "NSC", "academic_year": 2024},
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert resp.status_code == 201
        assert resp.json()["mark_count"] == 1

    def test_add_invalid_mark_422(self, tc: TestContext):
        learner = _create_learner(tc)
        resp = tc.school_client.post(
            f"/api/learners/{learner['learner_id']}/marks",
            json={"subject_name": "Mathematics", "score": 150, "exam_type": "NSC", "academic_year": 2024},
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert resp.status_code == 422

    def test_get_aps_score(self, tc: TestContext):
        learner = _create_learner(tc)
        tc.school_client.post(
            f"/api/learners/{learner['learner_id']}/marks",
            json={"subject_name": "Mathematics", "score": 80, "exam_type": "NSC", "academic_year": 2024},
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        resp = tc.school_client.get(f"/api/learners/{learner['learner_id']}/aps")
        assert resp.status_code == 200
        assert resp.json()["aps_score"] == 7

    def test_deactivate_learner(self, tc: TestContext):
        learner = _create_learner(tc)
        resp = tc.school_client.post(
            f"/api/learners/{learner['learner_id']}/deactivate",
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "Inactive"


# ─────────────────────────────────────────────────────────────────────────────
# Per-university APS scoring API tests (REQ-002)
# ─────────────────────────────────────────────────────────────────────────────

class TestPerUniversityAps:

    @pytest.fixture(scope="class")
    def client_with_rule(self):
        """A fresh TestContext with a synthetic ScoringRule pre-registered."""
        synthetic_uni_id = uuid4()
        repo = InMemoryScoringRuleRepository()
        rule = ScoringRule(
            university_id=synthetic_uni_id,
            band_thresholds=NSC_DEFAULT_SCORING_RULE.band_thresholds,
            subject_count=6,
            excluded_subjects=["Life Orientation"],
            subject_weightings={"Mathematics": 2.0},
        )
        repo.save(rule)
        ctx = _build_test_context(
            scoring_rule_repo=repo, university_id=synthetic_uni_id
        )
        return {"tc": ctx, "university_id": synthetic_uni_id}

    def _setup_learner_with_marks(self, ctx: TestContext) -> str:
        resp = ctx.school_client.post(
            "/api/learners",
            json={
                "full_name": "Naledi Dlamini",
                "school_id_number": "SRU-001",
                "grade": 12,
                "counselor_id": str(uuid4()),
                "school_id": str(ctx.school_id),
            },
            headers={"X-CSRF-Token": ctx.school_csrf},
        )
        assert resp.status_code == 201
        lid = resp.json()["learner_id"]
        for subj, score in [("Mathematics", 80), ("English", 70), ("Life Orientation", 50)]:
            r = ctx.school_client.post(
                f"/api/learners/{lid}/marks",
                json={"subject_name": subj, "score": score, "exam_type": "NSC", "academic_year": 2025},
                headers={"X-CSRF-Token": ctx.school_csrf},
            )
            assert r.status_code == 201
        return lid

    def test_aps_without_university_id_uses_default_formula(self, client_with_rule):
        ctx = client_with_rule["tc"]
        lid = self._setup_learner_with_marks(ctx)
        resp = ctx.school_client.get(f"/api/learners/{lid}/aps")
        assert resp.status_code == 200
        body = resp.json()
        assert body["aps_score"] == 17
        assert body["university_id"] is None

    def test_aps_with_registered_rule_applies_weighting_and_exclusion(self, client_with_rule):
        ctx = client_with_rule["tc"]
        uid = str(client_with_rule["university_id"])
        lid = self._setup_learner_with_marks(ctx)
        resp = ctx.school_client.get(f"/api/learners/{lid}/aps", params={"university_id": uid})
        assert resp.status_code == 200
        body = resp.json()
        assert body["aps_score"] == 20
        assert body["university_id"] == uid

    def test_aps_with_registered_rule_differs_from_default(self, client_with_rule):
        ctx = client_with_rule["tc"]
        uid = str(client_with_rule["university_id"])
        lid = self._setup_learner_with_marks(ctx)
        default_aps = ctx.school_client.get(f"/api/learners/{lid}/aps").json()["aps_score"]
        rule_aps = ctx.school_client.get(
            f"/api/learners/{lid}/aps", params={"university_id": uid}
        ).json()["aps_score"]
        assert default_aps != rule_aps

    def test_aps_unknown_university_falls_back_silently_with_null_id(self, client_with_rule):
        ctx = client_with_rule["tc"]
        lid = self._setup_learner_with_marks(ctx)
        resp = ctx.school_client.get(
            f"/api/learners/{lid}/aps", params={"university_id": str(uuid4())}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["aps_score"] == 17
        assert body["university_id"] is None

    def test_aps_unknown_university_matches_no_university_id(self, client_with_rule):
        ctx = client_with_rule["tc"]
        lid = self._setup_learner_with_marks(ctx)
        default = ctx.school_client.get(f"/api/learners/{lid}/aps").json()["aps_score"]
        fallback = ctx.school_client.get(
            f"/api/learners/{lid}/aps", params={"university_id": str(uuid4())}
        ).json()["aps_score"]
        assert default == fallback


# ─────────────────────────────────────────────────────────────────────────────
# Programme endpoints
# ─────────────────────────────────────────────────────────────────────────────

class TestProgrammeEndpoints:

    def test_create_programme(self, tc: TestContext):
        prog = _create_programme(tc)
        assert prog["name"] == "BSc Computer Science"
        assert prog["status"] == "Draft"
        assert prog["required_documents"] == ["ID", "Matric Certificate"]

    def test_get_programme(self, tc: TestContext):
        prog = _create_programme(tc)
        resp = tc.uni_client.get(f"/api/programmes/{prog['programme_id']}")
        assert resp.status_code == 200

    def test_get_nonexistent_programme_404(self, tc: TestContext):
        resp = tc.school_client.get(f"/api/programmes/{uuid4()}")
        assert resp.status_code == 404

    def test_list_programmes(self, tc: TestContext):
        _create_programme(tc)
        resp = tc.uni_client.get("/api/programmes")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_list_published_only(self, tc: TestContext):
        prog = _create_and_publish_programme(tc)
        resp = tc.school_client.get("/api/programmes?published_only=true")
        ids = [p["programme_id"] for p in resp.json()]
        assert prog["programme_id"] in ids
        for p in resp.json():
            assert p["is_active"] is True

    def test_update_programme(self, tc: TestContext):
        prog = _create_programme(tc)
        resp = tc.uni_client.put(
            f"/api/programmes/{prog['programme_id']}",
            json={"name": "BSc Data Science"},
            headers={"X-CSRF-Token": tc.uni_csrf},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "BSc Data Science"

    def test_update_programme_without_documents_preserves_existing_list(self, tc: TestContext):
        prog = _create_programme(tc)
        original_documents = prog["required_documents"]
        resp = tc.uni_client.put(
            f"/api/programmes/{prog['programme_id']}",
            json={"name": "BSc Data Science", "application_fee": "250.00"},
            headers={"X-CSRF-Token": tc.uni_csrf},
        )
        assert resp.status_code == 200
        assert resp.json()["required_documents"] == original_documents

    def test_update_programme_explicitly_replaces_required_documents(self, tc: TestContext):
        prog = _create_programme(tc)
        replacement = ["ID", "Latest Transcript"]
        resp = tc.uni_client.put(
            f"/api/programmes/{prog['programme_id']}",
            json={"required_documents": replacement},
            headers={"X-CSRF-Token": tc.uni_csrf},
        )
        assert resp.status_code == 200
        assert resp.json()["required_documents"] == replacement

    def test_delete_programme(self, tc: TestContext):
        prog = _create_programme(tc)
        assert tc.uni_client.delete(
            f"/api/programmes/{prog['programme_id']}",
            headers={"X-CSRF-Token": tc.uni_csrf},
        ).status_code == 204
        assert tc.school_client.get(f"/api/programmes/{prog['programme_id']}").status_code == 404

    def test_publish_programme(self, tc: TestContext):
        prog = _create_programme(tc)
        resp = tc.uni_client.post(
            f"/api/programmes/{prog['programme_id']}/publish",
            headers={"X-CSRF-Token": tc.uni_csrf},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "Published"

    def test_publish_expired_programme_400(self, tc: TestContext):
        prog = _create_programme(tc, deadline="2000-01-01")
        resp = tc.uni_client.post(
            f"/api/programmes/{prog['programme_id']}/publish",
            headers={"X-CSRF-Token": tc.uni_csrf},
        )
        assert resp.status_code == 400

    def test_deactivate_programme(self, tc: TestContext):
        prog = _create_and_publish_programme(tc)
        resp = tc.uni_client.post(
            f"/api/programmes/{prog['programme_id']}/deactivate",
            headers={"X-CSRF-Token": tc.uni_csrf},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "Deactivated"

    def test_extend_deadline(self, tc: TestContext):
        prog = _create_programme(tc)
        resp = tc.uni_client.post(
            f"/api/programmes/{prog['programme_id']}/extend-deadline",
            json={"new_deadline": "2100-01-01"},
            headers={"X-CSRF-Token": tc.uni_csrf},
        )
        assert resp.status_code == 200
        assert resp.json()["application_deadline"] == "2100-01-01"

    def test_eligibility_guaranteed(self, tc: TestContext):
        prog = _create_and_publish_programme(tc, aps=20)
        resp = tc.school_client.get(
            f"/api/programmes/{prog['programme_id']}/eligibility?learner_aps=24"
        )
        assert resp.status_code == 200
        assert resp.json()["eligibility"] == "Guaranteed"

    def test_eligibility_not_eligible(self, tc: TestContext):
        prog = _create_and_publish_programme(tc, aps=30)
        resp = tc.school_client.get(
            f"/api/programmes/{prog['programme_id']}/eligibility?learner_aps=20"
        )
        assert resp.status_code == 200
        assert resp.json()["eligibility"] == "NotEligible"


# ─────────────────────────────────────────────────────────────────────────────
# Eligibility endpoint (REQ-003)
# ─────────────────────────────────────────────────────────────────────────────

class TestEligibilityEndpoint:

    def test_without_learner_id_is_aps_only(self, tc: TestContext):
        prog = _create_and_publish_programme(tc, aps=20)
        resp = tc.school_client.get(
            f"/api/programmes/{prog['programme_id']}/eligibility?learner_aps=28"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["assessment_type"] == "APS_ONLY"
        assert body["subject_requirements_checked"] is False
        assert body["eligibility"] == "Guaranteed"

    def test_aps_only_with_programme_that_has_subject_requirements(self, tc: TestContext):
        prog = _create_and_publish_programme(tc, aps=20, required_subjects={"Mathematics": 60})
        resp = tc.school_client.get(
            f"/api/programmes/{prog['programme_id']}/eligibility?learner_aps=28"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["assessment_type"] == "APS_ONLY"
        assert body["has_subject_requirements"] is True
        assert body["subject_requirements_checked"] is False
        assert body["eligibility"] == "Guaranteed"

    def test_with_learner_id_uses_stored_marks_and_subject_requirements(self, tc: TestContext):
        learner = _create_learner(tc)
        lid = learner["learner_id"]
        tc.school_client.post(
            f"/api/learners/{lid}/marks",
            json={"subject_name": "Mathematics", "score": 65, "exam_type": "NSC", "academic_year": 2025},
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        prog = _create_and_publish_programme(tc, aps=20, required_subjects={"Mathematics": 60})
        resp = tc.school_client.get(
            f"/api/programmes/{prog['programme_id']}/eligibility?learner_aps=28&learner_id={lid}"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["assessment_type"] == "APS_AND_SUBJECTS"
        assert body["subject_requirements_checked"] is True
        assert body["has_subject_requirements"] is True
        assert body["eligibility"] == "Guaranteed"

    def test_with_learner_id_subject_not_met_returns_not_eligible(self, tc: TestContext):
        learner = _create_learner(tc)
        lid = learner["learner_id"]
        tc.school_client.post(
            f"/api/learners/{lid}/marks",
            json={"subject_name": "Mathematics", "score": 50, "exam_type": "NSC", "academic_year": 2025},
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        prog = _create_and_publish_programme(tc, aps=20, required_subjects={"Mathematics": 60})
        resp = tc.school_client.get(
            f"/api/programmes/{prog['programme_id']}/eligibility?learner_aps=35&learner_id={lid}"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["eligibility"] == "NotEligible"
        assert body["assessment_type"] == "APS_AND_SUBJECTS"

    def test_with_nonexistent_learner_id_returns_404(self, tc: TestContext):
        prog = _create_and_publish_programme(tc, aps=20)
        resp = tc.school_client.get(
            f"/api/programmes/{prog['programme_id']}/eligibility?learner_aps=28&learner_id={uuid4()}"
        )
        assert resp.status_code == 404

    def test_programme_without_subject_requirements_has_subject_requirements_false(self, tc: TestContext):
        prog = _create_and_publish_programme(tc, aps=20)
        resp = tc.school_client.get(
            f"/api/programmes/{prog['programme_id']}/eligibility?learner_aps=28"
        )
        assert resp.status_code == 200
        assert resp.json()["has_subject_requirements"] is False

    def test_update_programme_invalid_required_subject_mark_returns_400(self, tc: TestContext):
        prog = _create_programme(tc)
        resp = tc.uni_client.put(
            f"/api/programmes/{prog['programme_id']}",
            json={"required_subjects": {"Mathematics": 101}},
            headers={"X-CSRF-Token": tc.uni_csrf},
        )
        assert resp.status_code == 400

    def test_update_programme_negative_required_subject_mark_returns_400(self, tc: TestContext):
        prog = _create_programme(tc)
        resp = tc.uni_client.put(
            f"/api/programmes/{prog['programme_id']}",
            json={"required_subjects": {"Mathematics": -1}},
            headers={"X-CSRF-Token": tc.uni_csrf},
        )
        assert resp.status_code == 400

    def test_update_programme_valid_required_subjects_persisted(self, tc: TestContext):
        prog = _create_programme(tc)
        resp = tc.uni_client.put(
            f"/api/programmes/{prog['programme_id']}",
            json={"required_subjects": {"Mathematics": 60, "English": 50}},
            headers={"X-CSRF-Token": tc.uni_csrf},
        )
        assert resp.status_code == 200
        assert resp.json()["required_subjects"] == {"Mathematics": 60, "English": 50}

    def test_update_programme_clear_required_subjects(self, tc: TestContext):
        prog = _create_programme(tc, required_subjects={"Mathematics": 60})
        resp = tc.uni_client.put(
            f"/api/programmes/{prog['programme_id']}",
            json={"required_subjects": {}},
            headers={"X-CSRF-Token": tc.uni_csrf},
        )
        assert resp.status_code == 200
        assert resp.json()["required_subjects"] == {}


# ─────────────────────────────────────────────────────────────────────────────
# Application endpoints
# ─────────────────────────────────────────────────────────────────────────────

class TestApplicationEndpoints:

    def test_create_application(self, tc: TestContext):
        learner = _create_eligible_learner(tc)
        prog = _create_and_publish_programme(tc)
        app = _create_application(tc, learner["learner_id"], prog["programme_id"])
        assert app["status"] == "Draft"
        assert app["learner_id"] == learner["learner_id"]
        assert app["submission_ready"] is False
        assert "No application documents are linked." in app["submission_blockers"]

    def test_submit_rejects_missing_payment_and_document_prerequisites(self, tc: TestContext):
        learner = _create_eligible_learner(tc)
        programme = _create_and_publish_programme(tc)
        application = _create_application(
            tc, learner["learner_id"], programme["programme_id"]
        )

        response = tc.school_client.post(
            f"/api/applications/{application['application_id']}/submit",
            headers={"X-CSRF-Token": tc.school_csrf},
        )

        assert response.status_code == 409
        assert "payment reference" in response.json()["detail"]
        current = tc.school_client.get(
            f"/api/applications/{application['application_id']}"
        ).json()
        assert current["status"] == "Draft"
        assert current["submission_timestamp"] is None
        assert "No application documents are linked." in current["submission_blockers"]

    def test_submitted_status_requires_submission_endpoint(self, tc: TestContext):
        learner = _create_eligible_learner(tc)
        programme = _create_and_publish_programme(tc)
        application = _create_application(
            tc, learner["learner_id"], programme["programme_id"]
        )

        response = tc.school_client.put(
            f"/api/applications/{application['application_id']}/status",
            json={"new_status": "Submitted"},
            headers={"X-CSRF-Token": tc.school_csrf},
        )

        assert response.status_code == 409
        current = tc.school_client.get(
            f"/api/applications/{application['application_id']}"
        ).json()
        assert current["status"] == "Draft"

    def test_status_update_rejects_unverified_and_admissions_statuses(self, tc: TestContext):
        learner = _create_eligible_learner(tc)
        programme = _create_and_publish_programme(tc)
        application = _create_application(
            tc, learner["learner_id"], programme["programme_id"]
        )
        url = f"/api/applications/{application['application_id']}/status"
        headers = {"X-CSRF-Token": tc.school_csrf}

        fee_paid = tc.school_client.put(
            url,
            json={"new_status": "FeePaid"},
            headers=headers,
        )
        assert fee_paid.status_code == 409

        approval = tc.school_client.put(
            url,
            json={"new_status": "Accepted"},
            headers=headers,
        )
        assert approval.status_code == 403
        fee_paid = tc.school_client.put(
            url,
            json={"new_status": "FeePaid"},
            headers=headers,
        )
        assert fee_paid.status_code == 409
        package_ready = tc.school_client.put(
            url,
            json={"new_status": "PackageReady"},
            headers=headers,
        )
        assert package_ready.status_code == 409
        assert tc.school_client.get(
            f"/api/applications/{application['application_id']}"
        ).json()["status"] == "Draft"

    def test_create_application_learner_not_found_404(self, tc: TestContext):
        prog = _create_and_publish_programme(tc)
        resp = tc.school_client.post(
            "/api/applications",
            json={"learner_id": str(uuid4()), "programme_id": prog["programme_id"], "fee_amount": "200.00"},
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert resp.status_code == 404

    def test_create_application_programme_not_active_409(self, tc: TestContext):
        learner = _create_eligible_learner(tc)
        prog = _create_programme(tc)
        resp = tc.school_client.post(
            "/api/applications",
            json={"learner_id": learner["learner_id"], "programme_id": prog["programme_id"], "fee_amount": "200.00"},
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert resp.status_code == 409

    def test_ineligible_learner_application_422(self, tc: TestContext):
        learner = _create_learner(tc)
        prog = _create_and_publish_programme(tc, aps=28)
        resp = tc.school_client.post(
            "/api/applications",
            json={"learner_id": learner["learner_id"], "programme_id": prog["programme_id"], "fee_amount": "200.00"},
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == (
            "The learner does not meet the application eligibility requirements."
        )

    def test_duplicate_application_409(self, tc: TestContext):
        learner = _create_eligible_learner(tc)
        prog = _create_and_publish_programme(tc)
        _create_application(tc, learner["learner_id"], prog["programme_id"])
        resp = tc.school_client.post(
            "/api/applications",
            json={"learner_id": learner["learner_id"], "programme_id": prog["programme_id"], "fee_amount": "200.00"},
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert resp.status_code == 409

    def test_more_than_five_applications_allowed(self, tc: TestContext):
        learner = _create_eligible_learner(tc)
        for _ in range(7):
            prog = _create_and_publish_programme(tc)
            app = _create_application(tc, learner["learner_id"], prog["programme_id"])
            assert app["status"] == "Draft"

    def test_get_application(self, tc: TestContext):
        learner = _create_eligible_learner(tc)
        prog = _create_and_publish_programme(tc)
        app = _create_application(tc, learner["learner_id"], prog["programme_id"])
        resp = tc.school_client.get(f"/api/applications/{app['application_id']}")
        assert resp.status_code == 200

    def test_get_nonexistent_application_404(self, tc: TestContext):
        resp = tc.school_client.get(f"/api/applications/{uuid4()}")
        assert resp.status_code == 404

    def test_list_applications(self, tc: TestContext):
        resp = tc.school_client.get("/api/applications")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_learner_applications(self, tc: TestContext):
        learner = _create_eligible_learner(tc)
        prog = _create_and_publish_programme(tc)
        _create_application(tc, learner["learner_id"], prog["programme_id"])
        resp = tc.school_client.get(f"/api/applications/learner/{learner['learner_id']}")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_cancel_application(self, tc: TestContext):
        learner = _create_eligible_learner(tc)
        prog = _create_and_publish_programme(tc)
        app = _create_application(tc, learner["learner_id"], prog["programme_id"])
        note = "Learner withdrew the application"
        resp = tc.school_client.post(
            f"/api/applications/{app['application_id']}/cancel",
            json={"actor_id": ACTOR_ID, "note": note},
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "Cancelled"
        history = tc.school_client.get(f"/api/applications/{app['application_id']}/history")
        assert history.status_code == 200
        assert history.json()[0]["note"] == note

    def test_delete_application(self, tc: TestContext):
        learner = _create_eligible_learner(tc)
        prog = _create_and_publish_programme(tc)
        app = _create_application(tc, learner["learner_id"], prog["programme_id"])
        assert tc.school_client.delete(
            f"/api/applications/{app['application_id']}",
            headers={"X-CSRF-Token": tc.school_csrf},
        ).status_code == 204
        assert tc.school_client.get(f"/api/applications/{app['application_id']}").status_code == 404

    def test_fails_required_subject_mark_returns_422_no_record(self, tc: TestContext):
        learner = _create_learner(tc)
        for subj in ["English", "Life Sciences", "Physical Sciences", "History", "Geography"]:
            r = tc.school_client.post(
                f"/api/learners/{learner['learner_id']}/marks",
                json={"subject_name": subj, "score": 90, "exam_type": "NSC", "academic_year": 2024},
                headers={"X-CSRF-Token": tc.school_csrf},
            )
            assert r.status_code == 201
        r = tc.school_client.post(
            f"/api/learners/{learner['learner_id']}/marks",
            json={"subject_name": "Mathematics", "score": 40, "exam_type": "NSC", "academic_year": 2024},
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert r.status_code == 201
        prog = _create_and_publish_programme(tc, aps=28, required_subjects={"Mathematics": 60})
        resp = tc.school_client.post(
            "/api/applications",
            json={"learner_id": learner["learner_id"], "programme_id": prog["programme_id"], "fee_amount": "200.00"},
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == (
            "The learner does not meet the application eligibility requirements."
        )
        apps = tc.school_client.get(f"/api/applications/learner/{learner['learner_id']}").json()
        assert apps == []


class TestApplicationEligibilityEndpoint:

    def test_ineligible_warning_matches_application_creation_rules(self, tc: TestContext):
        learner = _create_learner(tc)
        prog = _create_and_publish_programme(
            tc, aps=28, required_subjects={"Mathematics": 60}
        )
        for subject in ["English", "Life Sciences", "Physical Sciences", "History", "Geography"]:
            resp = tc.school_client.post(
                f"/api/learners/{learner['learner_id']}/marks",
                json={
                    "subject_name": subject,
                    "score": 90,
                    "exam_type": "NSC",
                    "academic_year": 2025,
                },
                headers={"X-CSRF-Token": tc.school_csrf},
            )
            assert resp.status_code == 201, resp.text
        resp = tc.school_client.post(
            f"/api/learners/{learner['learner_id']}/marks",
            json={
                "subject_name": "Mathematics",
                "score": 50,
                "exam_type": "NSC",
                "academic_year": 2025,
            },
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert resp.status_code == 201, resp.text

        check = tc.school_client.get(
            f"/api/learners/{learner['learner_id']}/application-eligibility/"
            f"{prog['programme_id']}"
        )
        assert check.status_code == 200, check.text
        assert check.json()["eligibility"] == "NotEligible"
        assert check.json()["show_warning"] is True
        assert "compulsory subject requirements" in check.json()["warning_message"]

        created = tc.school_client.post(
            "/api/applications",
            json={
                "learner_id": learner["learner_id"],
                "programme_id": prog["programme_id"],
                "fee_amount": "200.00",
            },
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert created.status_code == 422
        assert tc.school_client.get(
            f"/api/applications/learner/{learner['learner_id']}"
        ).json() == []

    def test_warning_uses_the_programmes_university_scoring_rule(self):
        synthetic_uni_id = uuid4()
        scoring_rules = InMemoryScoringRuleRepository()
        scoring_rules.save(ScoringRule(
            university_id=synthetic_uni_id,
            band_thresholds=NSC_DEFAULT_SCORING_RULE.band_thresholds,
            subject_count=6,
            excluded_subjects=[],
            subject_weightings={"Mathematics": 2.0},
        ))
        ctx = _build_test_context(
            scoring_rule_repo=scoring_rules,
            university_id=synthetic_uni_id,
        )
        learner = _create_learner(ctx)
        for subject, score in [("Mathematics", 80), ("English", 70)]:
            added = ctx.school_client.post(
                f"/api/learners/{learner['learner_id']}/marks",
                json={
                    "subject_name": subject,
                    "score": score,
                    "exam_type": "NSC",
                    "academic_year": 2025,
                },
                headers={"X-CSRF-Token": ctx.school_csrf},
            )
            assert added.status_code == 201, added.text
        programme = _create_and_publish_programme(ctx, aps=15)

        check = ctx.school_client.get(
            f"/api/learners/{learner['learner_id']}/application-eligibility/"
            f"{programme['programme_id']}"
        )

        assert check.status_code == 200, check.text
        assert check.json()["learner_aps"] == 20
        assert check.json()["eligibility"] == "Guaranteed"
        assert check.json()["show_warning"] is False


class TestMarksAcademicYears:

    @pytest.mark.parametrize("grade", [11, 12])
    def test_capture_display_and_filter_marks_by_academic_year(
        self, tc: TestContext, grade: int
    ):
        learner_response = tc.school_client.post(
            "/api/learners",
            json={
                "full_name": f"Grade {grade} Learner",
                "school_id_number": f"YEAR-{grade}",
                "grade": grade,
                "counselor_id": str(uuid4()),
                "school_id": str(tc.school_id),
            },
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert learner_response.status_code == 201, learner_response.text
        learner_id = learner_response.json()["learner_id"]

        for year, score in [(2025, 72), (2026, 81)]:
            added = tc.school_client.post(
                f"/api/learners/{learner_id}/marks",
                json={
                    "subject_name": "Mathematics",
                    "score": score,
                    "exam_type": "NSC",
                    "academic_year": year,
                },
                headers={"X-CSRF-Token": tc.school_csrf},
            )
            assert added.status_code == 201, added.text

        all_marks = tc.school_client.get(f"/api/learners/{learner_id}/marks")
        assert all_marks.status_code == 200
        assert [(mark["academic_year"], mark["score"]) for mark in all_marks.json()] == [
            (2025, 72),
            (2026, 81),
        ]

        filtered = tc.school_client.get(
            f"/api/learners/{learner_id}/marks?academic_year=2025"
        )
        assert filtered.status_code == 200
        assert [(mark["academic_year"], mark["score"]) for mark in filtered.json()] == [
            (2025, 72)
        ]


class TestDashboardEligibilityDistribution:

    def test_distribution_uses_deterministic_published_programme_results(self):
        ctx = _build_test_context()
        learner = _create_eligible_learner(ctx)
        _create_and_publish_programme(ctx, aps=28)

        response = ctx.school_client.get("/api/dashboard/summary")

        assert response.status_code == 200, response.text
        summary = response.json()
        assert summary["eligibility_distribution"] == {
            "Guaranteed": 1,
            "Likely": 0,
            "Borderline": 0,
            "NotEligible": 0,
        }
        assert summary["total_learners"] == 1


class TestProgrammeRecommendations:

    def test_recommendation_explains_aps_and_unmet_subject_requirement(self):
        ctx = _build_test_context()
        learner = _create_learner(ctx)
        _add_marks_via_api(ctx, learner["learner_id"], score=90)
        programme = _create_and_publish_programme(
            ctx, aps=28, required_subjects={"Mathematics": 95}
        )

        response = ctx.school_client.get(
            f"/api/learners/{learner['learner_id']}/recommendations"
        )

        assert response.status_code == 200, response.text
        recommendations = response.json()["recommendations"]
        result = next(
            item for item in recommendations
            if item["programme_id"] == programme["programme_id"]
        )
        assert result["eligibility"] == "NotEligible"
        assert result["subject_requirements_met"] is False
        assert "Mathematics (minimum 95; recorded 90)" in result["explanation"]
        assert "APS 42 vs minimum 28" in result["explanation"]


class TestSensitiveRequestLogging:

    def test_request_log_excludes_path_and_credentials(self, tc: TestContext, caplog):
        learner_id = str(uuid4())
        password = "do-not-log-this-password"
        with caplog.at_level(logging.INFO, logger="unimatch.api"):
            response = tc.school_client.get(f"/api/learners/{learner_id}")

        assert response.status_code == 404
        assert learner_id not in caplog.text
        assert password not in caplog.text
        assert f"/api/learners/{learner_id}" not in caplog.text
        assert "method=GET status=404" in caplog.text

    def test_missing_required_subject_returns_422_no_record(self, tc: TestContext):
        learner = _create_learner(tc)
        for subj in ["English", "Life Sciences", "Physical Sciences", "History", "Geography", "Arts"]:
            r = tc.school_client.post(
                f"/api/learners/{learner['learner_id']}/marks",
                json={"subject_name": subj, "score": 90, "exam_type": "NSC", "academic_year": 2024},
                headers={"X-CSRF-Token": tc.school_csrf},
            )
            assert r.status_code == 201
        prog = _create_and_publish_programme(tc, aps=28, required_subjects={"Mathematics": 60})
        resp = tc.school_client.post(
            "/api/applications",
            json={"learner_id": learner["learner_id"], "programme_id": prog["programme_id"], "fee_amount": "200.00"},
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == (
            "The learner does not meet the application eligibility requirements."
        )
        apps = tc.school_client.get(f"/api/applications/learner/{learner['learner_id']}").json()
        assert apps == []


# ─────────────────────────────────────────────────────────────────────────────
# Application status history endpoint (REQ-007)
# ─────────────────────────────────────────────────────────────────────────────

class TestApplicationHistoryEndpoint:

    def test_history_empty_for_new_application(self, tc: TestContext):
        learner = _create_eligible_learner(tc)
        prog = _create_and_publish_programme(tc)
        app = _create_application(tc, learner["learner_id"], prog["programme_id"])
        resp = tc.school_client.get(f"/api/applications/{app['application_id']}/history")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_history_records_cancellation_all_fields(self, tc: TestContext):
        learner = _create_eligible_learner(tc)
        prog = _create_and_publish_programme(tc)
        app = _create_application(tc, learner["learner_id"], prog["programme_id"])

        cancel_resp = tc.school_client.post(
            f"/api/applications/{app['application_id']}/cancel",
            json={"actor_id": ACTOR_ID},
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert cancel_resp.status_code == 200

        resp = tc.school_client.get(f"/api/applications/{app['application_id']}/history")
        assert resp.status_code == 200
        entries = resp.json()
        assert len(entries) == 1

        entry = entries[0]
        assert entry["previous_status"] == "Draft"
        assert entry["new_status"] == "Cancelled"
        # changed_by is now derived from the authenticated principal (SchoolAdmin UUID)
        assert entry["changed_by"] == _school_admin_id(tc)
        assert entry["application_id"] == app["application_id"]
        assert entry["note"] == ""
        from uuid import UUID as _UUID
        _UUID(entry["entry_id"])
        from datetime import datetime
        datetime.fromisoformat(entry["changed_at"])

    def test_history_records_note_from_status_update(self, tc: TestContext):
        learner = _create_eligible_learner(tc)
        prog = _create_and_publish_programme(tc)
        app = _create_application(tc, learner["learner_id"], prog["programme_id"])

        update_resp = tc.school_client.put(
            f"/api/applications/{app['application_id']}/status",
            json={"new_status": "FeeOutstanding", "actor_id": ACTOR_ID, "note": "Fee request sent to learner"},
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert update_resp.status_code == 200

        resp = tc.school_client.get(f"/api/applications/{app['application_id']}/history")
        assert resp.status_code == 200
        entries = resp.json()
        assert len(entries) == 1
        assert entries[0]["previous_status"] == "Draft"
        assert entries[0]["new_status"] == "FeeOutstanding"
        assert entries[0]["note"] == "Fee request sent to learner"

    def test_history_chronological_order(self, tc: TestContext):
        learner = _create_eligible_learner(tc)
        prog = _create_and_publish_programme(tc)
        app = _create_application(tc, learner["learner_id"], prog["programme_id"])
        aid = app["application_id"]

        r1 = tc.school_client.put(
            f"/api/applications/{aid}/status",
            json={"new_status": "FeeOutstanding", "actor_id": ACTOR_ID, "note": "step 1"},
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert r1.status_code == 200

        r2 = tc.school_client.post(
            f"/api/applications/{aid}/cancel",
            json={"note": "step 2"},
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert r2.status_code == 200

        resp = tc.school_client.get(f"/api/applications/{aid}/history")
        assert resp.status_code == 200
        entries = resp.json()
        assert len(entries) == 2
        assert entries[0]["previous_status"] == "Draft"
        assert entries[0]["new_status"] == "FeeOutstanding"
        assert entries[1]["previous_status"] == "FeeOutstanding"
        assert entries[1]["new_status"] == "Cancelled"

        from datetime import datetime
        t0 = datetime.fromisoformat(entries[0]["changed_at"])
        t1 = datetime.fromisoformat(entries[1]["changed_at"])
        assert t0 <= t1

    def test_history_nonexistent_application_returns_404(self, tc: TestContext):
        resp = tc.school_client.get(f"/api/applications/{uuid4()}/history")
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Per-university APS at application creation (REQ-002)
# ─────────────────────────────────────────────────────────────────────────────

class TestPerUniversityApsApplicationCreation:

    @pytest.fixture(scope="class")
    def client_for_req002(self):
        synthetic_uni_id = uuid4()
        repo = InMemoryScoringRuleRepository()
        rule = ScoringRule(
            university_id=synthetic_uni_id,
            band_thresholds=NSC_DEFAULT_SCORING_RULE.band_thresholds,
            subject_count=6,
            excluded_subjects=["Mathematics"],
            subject_weightings={},
        )
        repo.save(rule)
        ctx = _build_test_context(scoring_rule_repo=repo, university_id=synthetic_uni_id)
        return {"tc": ctx, "university_id": str(synthetic_uni_id)}

    def test_university_rule_blocks_application_when_nsc_aps_passes(self, client_for_req002):
        ctx = client_for_req002["tc"]
        uni_id = client_for_req002["university_id"]

        resp = ctx.school_client.post(
            "/api/learners",
            json={
                "full_name": "Lerato Dube", "school_id_number": "REQ002-API-001",
                "grade": 12, "counselor_id": str(uuid4()), "school_id": str(ctx.school_id),
            },
            headers={"X-CSRF-Token": ctx.school_csrf},
        )
        assert resp.status_code == 201
        lid = resp.json()["learner_id"]

        for subj, score in [("Mathematics", 90), ("English", 70), ("Life Orientation", 50)]:
            r = ctx.school_client.post(
                f"/api/learners/{lid}/marks",
                json={"subject_name": subj, "score": score, "exam_type": "NSC", "academic_year": 2025},
                headers={"X-CSRF-Token": ctx.school_csrf},
            )
            assert r.status_code == 201

        resp = ctx.uni_client.post(
            "/api/programmes",
            json={
                "university_id": uni_id, "name": "BSc Engineering", "faculty": "Engineering",
                "minimum_aps": 12, "application_deadline": "2099-12-31",
                "application_fee": "300.00", "required_documents": ["ID"], "published_by": str(uuid4()),
            },
            headers={"X-CSRF-Token": ctx.uni_csrf},
        )
        assert resp.status_code == 201
        pid = resp.json()["programme_id"]
        assert ctx.uni_client.post(
            f"/api/programmes/{pid}/publish",
            headers={"X-CSRF-Token": ctx.uni_csrf},
        ).status_code == 200

        resp = ctx.school_client.post(
            "/api/applications",
            json={"learner_id": lid, "programme_id": pid, "fee_amount": "300.00"},
            headers={"X-CSRF-Token": ctx.school_csrf},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"] == (
            "The learner does not meet the application eligibility requirements."
        )

        apps = ctx.school_client.get(f"/api/applications/learner/{lid}").json()
        assert apps == []


# ─────────────────────────────────────────────────────────────────────────────
# Simulation endpoint (REQ-005)
# ─────────────────────────────────────────────────────────────────────────────

class TestSimulateEligibilityEndpoint:

    def _setup_learner_with_marks(self, ctx: TestContext, marks: dict) -> str:
        resp = ctx.school_client.post(
            "/api/learners",
            json={
                "full_name": "Naledi Simulation", "school_id_number": "SIM-001",
                "grade": 12, "counselor_id": str(uuid4()), "school_id": str(ctx.school_id),
            },
            headers={"X-CSRF-Token": ctx.school_csrf},
        )
        assert resp.status_code == 201
        lid = resp.json()["learner_id"]
        for subject, score in marks.items():
            r = ctx.school_client.post(
                f"/api/learners/{lid}/marks",
                json={"subject_name": subject, "score": score, "exam_type": "NSC", "academic_year": 2025},
                headers={"X-CSRF-Token": ctx.school_csrf},
            )
            assert r.status_code == 201
        return lid

    def _setup_programme(self, ctx: TestContext, aps: int) -> str:
        resp = ctx.uni_client.post(
            "/api/programmes",
            json={
                "university_id": str(ctx.university_id), "name": "BSc Simulation Test",
                "faculty": "Science", "minimum_aps": aps, "application_deadline": "2099-12-31",
                "application_fee": "200.00", "required_documents": ["ID"], "published_by": str(uuid4()),
            },
            headers={"X-CSRF-Token": ctx.uni_csrf},
        )
        assert resp.status_code == 201
        return resp.json()["programme_id"]

    def test_simulate_improves_eligibility_and_returns_simulation_flag(self, tc: TestContext):
        lid = self._setup_learner_with_marks(tc, {"Mathematics": 50, "English": 50})
        pid = self._setup_programme(tc, aps=9)

        resp = tc.school_client.post(
            f"/api/learners/{lid}/simulate-eligibility",
            json={"programme_id": pid, "overrides": {"Mathematics": 70}},
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["eligibility"] == "Guaranteed"
        assert body["simulated_aps"] == 14
        assert body["is_simulation"] is True

    def test_simulate_uses_registered_university_scoring_rule(self):
        synthetic_uni_id = uuid4()
        scoring_rules = InMemoryScoringRuleRepository()
        scoring_rules.save(ScoringRule(
            university_id=synthetic_uni_id,
            band_thresholds=NSC_DEFAULT_SCORING_RULE.band_thresholds,
            subject_count=6,
            excluded_subjects=[],
            subject_weightings={"Mathematics": 2.0},
        ))
        ctx = _build_test_context(scoring_rule_repo=scoring_rules, university_id=synthetic_uni_id)
        lid = self._setup_learner_with_marks(ctx, {"Mathematics": 80, "English": 70})
        pid = self._setup_programme(ctx, aps=15)

        response = ctx.school_client.post(
            f"/api/learners/{lid}/simulate-eligibility",
            json={"programme_id": pid, "overrides": {}},
            headers={"X-CSRF-Token": ctx.school_csrf},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["simulated_aps"] == 20
        assert body["university_rule_applied"] is True
        assert body["is_simulation"] is True

    def test_simulate_stored_marks_unchanged_after_endpoint_call(self, tc: TestContext):
        lid = self._setup_learner_with_marks(tc, {"Mathematics": 50})
        pid = self._setup_programme(tc, aps=9)
        marks_before = tc.school_client.get(f"/api/learners/{lid}").json()["mark_count"]

        tc.school_client.post(
            f"/api/learners/{lid}/simulate-eligibility",
            json={"programme_id": pid, "overrides": {"English": 80}},
            headers={"X-CSRF-Token": tc.school_csrf},
        )

        marks_after = tc.school_client.get(f"/api/learners/{lid}").json()["mark_count"]
        assert marks_after == marks_before

    def test_simulate_nonexistent_learner_returns_404(self, tc: TestContext):
        pid = self._setup_programme(tc, aps=20)
        resp = tc.school_client.post(
            f"/api/learners/{uuid4()}/simulate-eligibility",
            json={"programme_id": pid, "overrides": {}},
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert resp.status_code == 404

    def test_simulate_nonexistent_programme_returns_404(self, tc: TestContext):
        lid = self._setup_learner_with_marks(tc, {"Mathematics": 80})
        resp = tc.school_client.post(
            f"/api/learners/{lid}/simulate-eligibility",
            json={"programme_id": str(uuid4()), "overrides": {}},
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert resp.status_code == 404

    def test_simulate_invalid_override_score_returns_422(self, tc: TestContext):
        lid = self._setup_learner_with_marks(tc, {"Mathematics": 80})
        pid = self._setup_programme(tc, aps=20)
        resp = tc.school_client.post(
            f"/api/learners/{lid}/simulate-eligibility",
            json={"programme_id": pid, "overrides": {"Mathematics": 150}},
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert resp.status_code == 422

    def test_comparison_returns_current_and_projected_results_for_each_programme(self, tc: TestContext):
        lid = self._setup_learner_with_marks(tc, {"Mathematics": 50, "English": 50})
        pid1 = self._setup_programme(tc, aps=9)
        pid2 = self._setup_programme(tc, aps=15)
        marks_before = tc.school_client.get(f"/api/learners/{lid}").json()["mark_count"]
        apps_before = tc.school_client.get(f"/api/applications/learner/{lid}").json()

        response = tc.school_client.post(
            f"/api/learners/{lid}/simulate-eligibility/comparison",
            json={"programme_ids": [pid1, pid2], "overrides": {"Mathematics": 70}},
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["is_simulation"] is True
        assert [item["programme_id"] for item in body["results"]] == [pid1, pid2]
        assert all(item["current_aps"] == 8 for item in body["results"])
        assert all(item["projected_aps"] == 14 for item in body["results"])
        assert body["results"][0]["projected_eligibility"] == "Guaranteed"
        assert body["results"][1]["projected_eligibility"] == "NotEligible"
        assert tc.school_client.get(f"/api/learners/{lid}").json()["mark_count"] == marks_before
        assert tc.school_client.get(f"/api/applications/learner/{lid}").json() == apps_before

    def test_comparison_uses_programme_university_scoring_rule(self):
        synthetic_uni_id = uuid4()
        scoring_rules = InMemoryScoringRuleRepository()
        scoring_rules.save(ScoringRule(
            university_id=synthetic_uni_id,
            band_thresholds=NSC_DEFAULT_SCORING_RULE.band_thresholds,
            subject_count=6,
            excluded_subjects=[],
            subject_weightings={"Mathematics": 2.0},
        ))
        ctx = _build_test_context(scoring_rule_repo=scoring_rules, university_id=synthetic_uni_id)
        lid = self._setup_learner_with_marks(ctx, {"Mathematics": 80, "English": 70})
        pid = self._setup_programme(ctx, aps=20)
        standard_aps = ctx.school_client.get(f"/api/learners/{lid}/aps").json()["aps_score"]

        response = ctx.school_client.post(
            f"/api/learners/{lid}/simulate-eligibility/comparison",
            json={"programme_ids": [pid], "overrides": {"Mathematics": 90}},
            headers={"X-CSRF-Token": ctx.school_csrf},
        )
        assert response.status_code == 200
        result = response.json()["results"][0]
        assert result["current_aps"] == 20
        assert result["current_aps"] != standard_aps
        assert result["projected_aps"] > result["current_aps"]
        assert result["university_rule_applied"] is True

    def test_comparison_rejects_invalid_marks_without_changing_records(self, tc: TestContext):
        lid = self._setup_learner_with_marks(tc, {"Mathematics": 80})
        pid = self._setup_programme(tc, aps=20)
        marks_before = tc.school_client.get(f"/api/learners/{lid}").json()["mark_count"]
        apps_before = tc.school_client.get(f"/api/applications/learner/{lid}").json()

        response = tc.school_client.post(
            f"/api/learners/{lid}/simulate-eligibility/comparison",
            json={"programme_ids": [pid], "overrides": {"Mathematics": 101}},
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert response.status_code == 422
        assert tc.school_client.get(f"/api/learners/{lid}").json()["mark_count"] == marks_before
        assert tc.school_client.get(f"/api/applications/learner/{lid}").json() == apps_before


class TestStage3InMemoryOperations:

    def test_guidance_session_is_scoped_and_staff_actor_is_derived(self, tc: TestContext):
        learner = _create_learner(tc)
        response = tc.school_client.post(
            f"/api/learners/{learner['learner_id']}/guidance-sessions",
            json={
                "session_date": "2026-10-30",
                "purpose": "Programme planning",
                "notes": "Discussed next steps.",
            },
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert response.status_code == 201, response.text
        session = response.json()
        assert session["school_id"] == str(tc.school_id)
        assert session["responsible_staff_id"] == _school_admin_id(tc)
        history = tc.school_client.get(
            f"/api/learners/{learner['learner_id']}/guidance-sessions"
        )
        assert history.status_code == 200
        assert [item["guidance_session_id"] for item in history.json()] == [
            session["guidance_session_id"]
        ]

        updated = tc.school_client.put(
            f"/api/guidance-sessions/{session['guidance_session_id']}",
            json={"status": "Completed"},
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert updated.status_code == 200
        assert updated.json()["status"] == "Completed"
        audit = tc.school_client.get("/api/audit").json()
        guidance_event = next(
            item for item in audit
            if item["target_id"] == session["guidance_session_id"]
            and item["action"] == "guidance_session.created"
        )
        assert "Discussed next steps." not in str(guidance_event)

    def test_application_notifications_and_audit_use_authenticated_actor(self, tc: TestContext):
        learner = _create_eligible_learner(tc)
        programme = _create_and_publish_programme(tc)
        application = _create_application(
            tc, learner["learner_id"], programme["programme_id"]
        )

        notifications = tc.school_client.get("/api/notifications")
        assert notifications.status_code == 200
        assert any(
            item["type"] == "application.created"
            for item in notifications.json()
        )
        notice = next(
            item for item in notifications.json()
            if item["type"] == "application.created"
        )
        marked = tc.school_client.post(
            f"/api/notifications/{notice['notification_id']}/read",
            headers={"X-CSRF-Token": tc.school_csrf},
        )
        assert marked.status_code == 200
        assert marked.json()["status"] == "Read"

        audit = tc.school_client.get("/api/audit")
        assert audit.status_code == 200
        event = next(
            item for item in audit.json()
            if item["target_id"] == application["application_id"]
            and item["action"] == "application.created"
        )
        assert event["actor_id"] == _school_admin_id(tc)
        assert "full_name" not in str(event["new_value"])

    def test_school_scoring_rule_management_uses_university_principal(self):
        ctx = _build_test_context()
        current = ctx.uni_client.get("/api/universities/me/scoring-rule")
        assert current.status_code == 200, current.text
        assert current.json()["university_id"] == str(ctx.university_id)
        assert current.json()["is_customized"] is False

        saved = ctx.uni_client.put(
            "/api/universities/me/scoring-rule",
            json={
                "band_thresholds": [[80, 7], [70, 6], [60, 5]],
                "subject_count": 5,
                "excluded_subjects": ["Life Orientation"],
                "subject_weightings": {"Mathematics": 1.5},
            },
            headers={"X-CSRF-Token": ctx.uni_csrf},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["is_customized"] is True
        assert saved.json()["subject_count"] == 5

        school_attempt = ctx.school_client.put(
            "/api/universities/me/scoring-rule",
            json={
                "band_thresholds": [[80, 7]],
                "subject_count": 6,
                "excluded_subjects": [],
                "subject_weightings": {},
            },
            headers={"X-CSRF-Token": ctx.school_csrf},
        )
        assert school_attempt.status_code == 403

    def test_invalid_scoring_rule_does_not_replace_existing_rule(self):
        ctx = _build_test_context()
        invalid = ctx.uni_client.put(
            "/api/universities/me/scoring-rule",
            json={
                "band_thresholds": [[70, 6], [70, 7]],
                "subject_count": 6,
                "excluded_subjects": [],
                "subject_weightings": {},
            },
            headers={"X-CSRF-Token": ctx.uni_csrf},
        )
        assert invalid.status_code == 400
        current = ctx.uni_client.get("/api/universities/me/scoring-rule")
        assert current.status_code == 200
        assert current.json()["is_customized"] is False

    def test_school_report_uses_actual_learners_applications_and_eligibility(self):
        ctx = _build_test_context()
        learner = _create_eligible_learner(ctx)
        programme = _create_and_publish_programme(ctx)
        _create_application(ctx, learner["learner_id"], programme["programme_id"])

        report = ctx.school_client.get("/api/reports/school")

        assert report.status_code == 200, report.text
        body = report.json()
        assert body["total_learners"] == 1
        assert body["learners_with_marks"] == 1
        assert body["total_applications"] == 1
        assert body["applications_by_status"] == {"Draft": 1}
        assert body["eligibility_distribution"]["Guaranteed"] == 1
        assert body["upcoming_deadlines"][0]["programme_id"] == programme["programme_id"]

    def test_deadline_notifications_are_persisted_idempotently_without_learner_pii(self):
        ctx = _build_test_context()
        learner = _create_eligible_learner(ctx)
        deadline = (date.today() + timedelta(days=10)).isoformat()
        programme = _create_programme(ctx, deadline=deadline)
        programme = _publish_programme(ctx, programme["programme_id"])
        _create_application(ctx, learner["learner_id"], programme["programme_id"])

        first = ctx.school_client.post(
            "/api/notifications/deadline-reminders",
            headers={"X-CSRF-Token": ctx.school_csrf},
        )
        second = ctx.school_client.post(
            "/api/notifications/deadline-reminders",
            headers={"X-CSRF-Token": ctx.school_csrf},
        )
        assert first.status_code == second.status_code == 200
        assert first.json()["created"] == 1
        assert second.json()["created"] == 0
        reminders = ctx.school_client.get("/api/notifications")
        assert reminders.status_code == 200
        deadline_notices = [
            item for item in reminders.json()
            if item["type"] == "application.deadline"
        ]
        assert len(deadline_notices) == 1
        assert learner["full_name"] not in deadline_notices[0]["message"]

    def test_doe_reporting_suppresses_small_cohorts_and_hides_school_users(self, tc: TestContext):
        ctx = _build_test_context()
        learners = [
            _create_learner(
                ctx,
                full_name=f"Private Learner {index}",
                school_id_number=f"PRIVATE-{index}",
            )
            for index in range(1, 5)
        ]
        for learner in learners:
            _add_marks_via_api(ctx, learner["learner_id"])
        programme = _create_and_publish_programme(ctx)
        applications = [
            _create_application(ctx, learner["learner_id"], programme["programme_id"])
            for learner in learners
        ]

        response = ctx.doe_client.get("/api/reports/doe")
        assert response.status_code == 200, response.text
        report = response.json()
        assert report["suppressed"] is True
        assert report["cohort_size"] is None
        assert report["total_learners"] is None
        assert report["total_applications"] is None
        assert all(value is None for value in report["applications_by_status"].values())
        assert all(value is None for value in report["eligibility_distribution"].values())
        assert not any(
            key in report
            for key in ("learner_id", "full_name", "school_id", "school_id_number")
        )
        serialized = response.text
        assert all(learner["full_name"] not in serialized for learner in learners)
        assert all(learner["learner_id"] not in serialized for learner in learners)
        assert all(
            application["application_id"] not in serialized
            for application in applications
        )
        assert tc.school_client.get("/api/reports/doe").status_code == 403

    def test_doe_report_suppresses_totals_that_could_reveal_small_status_buckets(self):
        ctx = _build_test_context()
        for index in range(1, 6):
            _create_learner(
                ctx,
                full_name=f"Private Learner {index}",
                school_id_number=f"PRIVATE-{index}",
            )
        programme = _create_and_publish_programme(ctx)
        learner = _create_learner(
            ctx, full_name="Sixth Private Learner", school_id_number="PRIVATE-6"
        )
        _add_marks_via_api(ctx, learner["learner_id"])
        _create_application(ctx, learner["learner_id"], programme["programme_id"])

        response = ctx.doe_client.get("/api/reports/doe")

        assert response.status_code == 200, response.text
        report = response.json()
        assert report["cohort_size"] == 6
        assert report["total_learners"] == 6
        assert report["total_applications"] is None
        assert report["applications_by_status"] == {"Draft": None}
        assert report["suppressed"] is True
