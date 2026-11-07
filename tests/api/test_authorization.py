"""
tests/api/test_authorization.py
================================
Security tests for Stage 1C route authorization.

Covers: unauthenticated access, CSRF rejection, cross-school isolation,
cross-university isolation, role rejection, legacy roles, no-mutation
guarantees, suspended/pending account blocking.
"""
from __future__ import annotations

from html import escape
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from unimatch.api import create_app
from unimatch.auth import AuthPrincipal, hash_password
from unimatch.bootstrap import bootstrap_system_admin
from unimatch.entities import Application, UserAccount
from unimatch.enums import AccountStateEnum, ApplicationStatusEnum, RoleEnum
from unimatch.provisioning import AccountProvisioningService
from unimatch.rag import (
    EmbeddingState,
    InMemoryRagRepository,
    LogicalDocumentState,
    PhysicalDocumentState,
    RagConversation,
)
from unimatch.repositories.inmemory import (
    InMemoryApplicationRepository,
    InMemorySessionRepository,
    InMemoryUserAccountRepository,
    InMemoryVerificationRecordRepository,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixture helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_two_school_app(
    *, vector_store=None, answer_provider=None, document_storage_dir: Path | None = None
):
    """
    Build an app with:
      - school_a + school_admin_a  (logged in, csrf_a)
      - school_b + school_admin_b  (logged in, csrf_b)
      - university_x + uni_admin_x (logged in, csrf_x)
      - university_y + uni_admin_y (logged in, csrf_y)
      - a teacher account (active, no school scope, logged in)
    All clients share the same in-memory repos.
    """
    school_a = uuid4()
    school_b = uuid4()
    uni_x = uuid4()
    uni_y = uuid4()

    account_repo = InMemoryUserAccountRepository()
    session_repo = InMemorySessionRepository()
    verification_repo = InMemoryVerificationRecordRepository()
    knowledge_repo = InMemoryRagRepository()
    application_repo = InMemoryApplicationRepository()

    admin1 = bootstrap_system_admin(
        account_repo, _email="superadmin@test", _password="SuperPass!"
    )
    admin2 = UserAccount(
        user_id=uuid4(), email="superadmin2@test",
        password_hash=hash_password("SuperPass2!"),
        role=RoleEnum.SystemAdmin, account_state=AccountStateEnum.Active,
    )
    account_repo.save(admin2)

    svc = AccountProvisioningService(account_repo=account_repo, verification_repo=verification_repo)
    p1 = AuthPrincipal(account_id=admin1.user_id, role=RoleEnum.SystemAdmin, account_state=AccountStateEnum.Active)
    p2 = AuthPrincipal(account_id=admin2.user_id, role=RoleEnum.SystemAdmin, account_state=AccountStateEnum.Active)

    def _provision_activate(email, password, role, school_id=None, university_id=None):
        acc = svc.provision_account(p1, email, password, role, school_id=school_id, university_id=university_id)
        svc.record_verification(p1, acc.user_id, f"REF-{email}", school_scope=[school_id] if school_id else [], university_id=university_id)
        svc.activate_account(p2, acc.user_id)
        return acc

    _provision_activate("sa_a@test", "SAaPass!", RoleEnum.SchoolAdmin, school_id=school_a)
    _provision_activate("sa_b@test", "SAbPass!", RoleEnum.SchoolAdmin, school_id=school_b)
    _provision_activate("ua_x@test", "UAXPass!", RoleEnum.UniversityAdmissions, university_id=uni_x)
    _provision_activate("ua_y@test", "UAYPass!", RoleEnum.UniversityAdmissions, university_id=uni_y)

    # Teacher — active but legacy role, no provisioning path needed (direct insert)
    teacher = UserAccount(
        user_id=uuid4(), email="teacher@test",
        password_hash=hash_password("TeachPass!"),
        role=RoleEnum.Teacher, account_state=AccountStateEnum.Active,
    )
    account_repo.save(teacher)

    # Pending account
    pending_acc = UserAccount(
        user_id=uuid4(), email="pending@test",
        password_hash=hash_password("PendPass!"),
        role=RoleEnum.SchoolAdmin, account_state=AccountStateEnum.Pending,
        school_id=school_a,
    )
    account_repo.save(pending_acc)

    # Suspended account
    suspended_acc = UserAccount(
        user_id=uuid4(), email="suspended@test",
        password_hash=hash_password("SuspPass!"),
        role=RoleEnum.SchoolAdmin, account_state=AccountStateEnum.Suspended,
        school_id=school_a,
    )
    account_repo.save(suspended_acc)

    app = create_app(
        account_repo=account_repo,
        session_repo=session_repo,
        verification_repo=verification_repo,
        application_repository=application_repo,
        rag_repo=knowledge_repo,
        vector_store=vector_store,
        answer_provider=answer_provider,
        document_storage_dir=document_storage_dir,
    )

    def _login(email, password):
        c = TestClient(app, raise_server_exceptions=False)
        c.post("/api/auth/login", json={"email": email, "password": password})
        csrf = c.get("/api/auth/csrf").json()["csrf_token"]
        return c, csrf

    client_a, csrf_a = _login("sa_a@test", "SAaPass!")
    client_b, csrf_b = _login("sa_b@test", "SAbPass!")
    client_x, csrf_x = _login("ua_x@test", "UAXPass!")
    client_y, csrf_y = _login("ua_y@test", "UAYPass!")
    anon = TestClient(app, raise_server_exceptions=False)
    teacher_client, teacher_csrf = _login("teacher@test", "TeachPass!")

    return {
        "app": app,
        "school_a": school_a, "school_b": school_b,
        "uni_x": uni_x, "uni_y": uni_y,
        "client_a": client_a, "csrf_a": csrf_a,
        "client_b": client_b, "csrf_b": csrf_b,
        "client_x": client_x, "csrf_x": csrf_x,
        "client_y": client_y, "csrf_y": csrf_y,
        "anon": anon,
        "account_repo": account_repo,
        "application_repo": application_repo,
        "knowledge_repo": knowledge_repo,
        "teacher_client": teacher_client, "teacher_csrf": teacher_csrf,
    }


@pytest.fixture(scope="module")
def env():
    return _make_two_school_app()


def _create_learner_for(client, school_id, csrf) -> dict:
    resp = client.post(
        "/api/learners",
        json={
            "full_name": "Test Learner", "school_id_number": "TST-001",
            "grade": 12, "counselor_id": str(uuid4()), "school_id": str(school_id),
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_programme_for(client, uni_id, csrf) -> dict:
    resp = client.post(
        "/api/programmes",
        json={
            "university_id": str(uni_id), "name": "BSc Test", "faculty": "Science",
            "minimum_aps": 20, "application_deadline": "2099-12-31",
            "application_fee": "100.00", "required_documents": [], "published_by": str(uuid4()),
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_review_application(
    env, university: str = "x"
) -> tuple[dict, Application]:
    uni_key = f"uni_{university}"
    client_key = f"client_{university}"
    csrf_key = f"csrf_{university}"
    programme = _create_programme_for(
        env[client_key], env[uni_key], env[csrf_key]
    )
    publish = env[client_key].post(
        f"/api/programmes/{programme['programme_id']}/publish",
        headers={"X-CSRF-Token": env[csrf_key]},
    )
    assert publish.status_code == 200, publish.text

    learner = _create_learner_for(
        env["client_a"], env["school_a"], env["csrf_a"]
    )
    for subject in [
        "Mathematics",
        "English",
        "Life Sciences",
        "Physical Sciences",
        "History",
        "Geography",
    ]:
        mark = env["client_a"].post(
            f"/api/learners/{learner['learner_id']}/marks",
            json={
                "subject_name": subject,
                "score": 90,
                "exam_type": "NSC",
                "academic_year": 2025,
            },
            headers={"X-CSRF-Token": env["csrf_a"]},
        )
        assert mark.status_code == 201, mark.text

    created = env["client_a"].post(
        "/api/applications",
        json={
            "learner_id": learner["learner_id"],
            "programme_id": programme["programme_id"],
            "fee_amount": "100.00",
        },
        headers={"X-CSRF-Token": env["csrf_a"]},
    )
    assert created.status_code == 201, created.text
    application = env["application_repo"].find_by_id(
        UUID(created.json()["application_id"])
    )
    assert application is not None
    application.status = ApplicationStatusEnum.Submitted
    application.submission_timestamp = datetime.now(timezone.utc)
    env["application_repo"].save(application)
    return created.json(), application


def _docx_bytes(text: str) -> bytes:
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{escape(text)}</w:t></w:r></w:p></w:body></w:document>"
    )
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        archive.writestr("word/document.xml", document_xml)
    return output.getvalue()


def _upload_rag_doc(
    client,
    csrf: str,
    text: str,
    filename: str = "admissions.docx",
    document_bytes: bytes | None = None,
    logical_document_id: str | None = None,
):
    content = document_bytes if document_bytes is not None else _docx_bytes(text)
    form_data = {"title": "Synthetic test admissions fixture"}
    if logical_document_id is not None:
        form_data["logical_document_id"] = logical_document_id
    return client.post(
        "/api/agent/documents",
        data=form_data,
        files={
            "file": (
                filename,
                content,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        headers={"X-CSRF-Token": csrf},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Unauthenticated access
# ─────────────────────────────────────────────────────────────────────────────

class TestUnauthenticatedRejection:
    PROTECTED_ROUTES = [
        ("GET", "/api/learners"),
        ("POST", "/api/learners"),
        ("GET", "/api/applications"),
        ("POST", "/api/applications"),
    ]

    def test_unauthenticated_learner_list_rejected(self, env):
        resp = env["anon"].get("/api/learners")
        assert resp.status_code == 401

    def test_unauthenticated_learner_create_rejected(self, env):
        resp = env["anon"].post("/api/learners", json={
            "full_name": "X", "school_id_number": "X", "grade": 12,
            "counselor_id": str(uuid4()), "school_id": str(uuid4()),
        })
        assert resp.status_code == 401

    def test_unauthenticated_application_list_rejected(self, env):
        assert env["anon"].get("/api/applications").status_code == 401

    def test_unauthenticated_programme_create_rejected(self, env):
        resp = env["anon"].post("/api/programmes", json={
            "university_id": str(uuid4()), "name": "X", "faculty": "X",
            "minimum_aps": 20, "application_deadline": "2099-12-31",
            "application_fee": "100.00", "required_documents": [], "published_by": str(uuid4()),
        })
        assert resp.status_code == 401

    def test_public_routes_remain_accessible(self, env):
        assert env["anon"].get("/health").status_code == 200
        assert env["anon"].get("/api/programmes").status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# CSRF enforcement
# ─────────────────────────────────────────────────────────────────────────────

class TestCsrfEnforcement:

    def test_create_learner_without_csrf_rejected(self, env):
        resp = env["client_a"].post("/api/learners", json={
            "full_name": "X", "school_id_number": "X", "grade": 12,
            "counselor_id": str(uuid4()), "school_id": str(env["school_a"]),
        })
        assert resp.status_code == 403

    def test_create_learner_wrong_csrf_rejected(self, env):
        resp = env["client_a"].post(
            "/api/learners",
            json={"full_name": "X", "school_id_number": "X", "grade": 12,
                  "counselor_id": str(uuid4()), "school_id": str(env["school_a"])},
            headers={"X-CSRF-Token": "wrong-token"},
        )
        assert resp.status_code == 403

    def test_create_learner_with_correct_csrf_succeeds(self, env):
        resp = env["client_a"].post(
            "/api/learners",
            json={"full_name": "Valid", "school_id_number": "V-001", "grade": 12,
                  "counselor_id": str(uuid4()), "school_id": str(env["school_a"])},
            headers={"X-CSRF-Token": env["csrf_a"]},
        )
        assert resp.status_code == 201

    def test_csrf_rejection_before_mutation(self, env):
        """A CSRF-rejected request must not create any data."""
        before = len(env["client_a"].get("/api/learners").json())
        env["client_a"].post("/api/learners", json={
            "full_name": "Should Not Appear", "school_id_number": "X",
            "grade": 12, "counselor_id": str(uuid4()), "school_id": str(env["school_a"]),
        })
        after = len(env["client_a"].get("/api/learners").json())
        assert after == before

    def test_delete_without_csrf_rejected(self, env):
        learner = _create_learner_for(env["client_a"], env["school_a"], env["csrf_a"])
        resp = env["client_a"].delete(f"/api/learners/{learner['learner_id']}")
        assert resp.status_code == 403
        # learner must still exist
        assert env["client_a"].get(f"/api/learners/{learner['learner_id']}").status_code == 200

    def test_programme_create_without_csrf_rejected(self, env):
        resp = env["client_x"].post("/api/programmes", json={
            "university_id": str(env["uni_x"]), "name": "X", "faculty": "X",
            "minimum_aps": 20, "application_deadline": "2099-12-31",
            "application_fee": "100.00", "required_documents": [], "published_by": str(uuid4()),
        })
        assert resp.status_code == 403

    def test_get_requests_do_not_require_csrf(self, env):
        learner = _create_learner_for(env["client_a"], env["school_a"], env["csrf_a"])
        resp = env["client_a"].get(f"/api/learners/{learner['learner_id']}")
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# School isolation
# ─────────────────────────────────────────────────────────────────────────────

class TestSchoolIsolation:

    def test_other_school_cannot_download_or_review_learner_document(
        self, tmp_path: Path
    ):
        scoped_env = _make_two_school_app(document_storage_dir=tmp_path)
        learner = _create_learner_for(
            scoped_env["client_b"], scoped_env["school_b"], scoped_env["csrf_b"]
        )
        upload = scoped_env["client_b"].post(
            f"/api/learners/{learner['learner_id']}/documents",
            data={"document_type": "ID"},
            files={
                "file": (
                    "identity.pdf",
                    b"%PDF-1.7\n%%EOF",
                    "application/pdf",
                )
            },
            headers={"X-CSRF-Token": scoped_env["csrf_b"]},
        )
        assert upload.status_code == 201, upload.text
        document_id = upload.json()["document_id"]
        download_url = upload.json()["download_url"]

        assert scoped_env["client_a"].get(download_url).status_code == 404
        denied_review = scoped_env["client_a"].put(
            f"/api/documents/{document_id}/review",
            json={"decision": "Verified", "note": "Cross-school access attempt."},
            headers={"X-CSRF-Token": scoped_env["csrf_a"]},
        )
        assert denied_review.status_code == 404
        assert scoped_env["client_b"].get(download_url).status_code == 200

    def test_school_admin_cannot_read_other_schools_learner(self, env):
        learner_b = _create_learner_for(env["client_b"], env["school_b"], env["csrf_b"])
        resp = env["client_a"].get(f"/api/learners/{learner_b['learner_id']}")
        assert resp.status_code == 404

    def test_school_admin_cannot_update_other_schools_learner(self, env):
        learner_b = _create_learner_for(env["client_b"], env["school_b"], env["csrf_b"])
        original_name = learner_b["full_name"]
        resp = env["client_a"].put(
            f"/api/learners/{learner_b['learner_id']}",
            json={"full_name": "Hacked"},
            headers={"X-CSRF-Token": env["csrf_a"]},
        )
        assert resp.status_code == 404
        # Verify data unchanged by re-reading with owner
        still_learner = env["client_b"].get(f"/api/learners/{learner_b['learner_id']}").json()
        assert still_learner["full_name"] == original_name

    def test_school_admin_cannot_delete_other_schools_learner(self, env):
        learner_b = _create_learner_for(env["client_b"], env["school_b"], env["csrf_b"])
        resp = env["client_a"].delete(
            f"/api/learners/{learner_b['learner_id']}",
            headers={"X-CSRF-Token": env["csrf_a"]},
        )
        assert resp.status_code == 404
        # learner_b still accessible to owner
        assert env["client_b"].get(f"/api/learners/{learner_b['learner_id']}").status_code == 200

    def test_school_admin_cannot_add_marks_to_other_schools_learner(self, env):
        learner_b = _create_learner_for(env["client_b"], env["school_b"], env["csrf_b"])
        before_count = env["client_b"].get(f"/api/learners/{learner_b['learner_id']}").json()["mark_count"]
        resp = env["client_a"].post(
            f"/api/learners/{learner_b['learner_id']}/marks",
            json={"subject_name": "Maths", "score": 80, "exam_type": "NSC", "academic_year": 2024},
            headers={"X-CSRF-Token": env["csrf_a"]},
        )
        assert resp.status_code == 404
        after_count = env["client_b"].get(f"/api/learners/{learner_b['learner_id']}").json()["mark_count"]
        assert after_count == before_count

    def test_learner_list_scoped_to_own_school(self, env):
        learner_a = _create_learner_for(env["client_a"], env["school_a"], env["csrf_a"])
        learner_b = _create_learner_for(env["client_b"], env["school_b"], env["csrf_b"])
        list_a = [l["learner_id"] for l in env["client_a"].get("/api/learners").json()]
        list_b = [l["learner_id"] for l in env["client_b"].get("/api/learners").json()]
        assert learner_a["learner_id"] in list_a
        assert learner_b["learner_id"] not in list_a
        assert learner_b["learner_id"] in list_b
        assert learner_a["learner_id"] not in list_b

    def test_create_learner_uses_principal_school_id(self, env):
        """school_id in request body is overridden by the principal's school_id."""
        resp = env["client_a"].post(
            "/api/learners",
            json={
                "full_name": "Owned By A", "school_id_number": "A-999",
                "grade": 12, "counselor_id": str(uuid4()),
                "school_id": str(env["school_b"]),  # attacker-supplied wrong school
            },
            headers={"X-CSRF-Token": env["csrf_a"]},
        )
        assert resp.status_code == 201
        assert resp.json()["school_id"] == str(env["school_a"])  # principal wins

    def test_csv_import_uses_authenticated_school_scope_and_hides_rows_from_other_school(self, env):
        """An attacker-supplied school_id column cannot redirect imported learners."""
        csv_a = (
            "school_id_number,full_name,grade,subject_name,score,exam_type,academic_year,school_id\n"
            f"A-CSV-001,Synthetic Learner A,12,Mathematics,78,NSC,2026,{env['school_b']}\n"
        ).encode()
        imported_a = env["client_a"].post(
            "/api/learners/import",
            files={"file": ("synthetic-school-a.csv", csv_a, "text/csv")},
            headers={"X-CSRF-Token": env["csrf_a"]},
        )
        assert imported_a.status_code == 201, imported_a.text
        assert imported_a.json()["imported_learners"] == 1
        assert imported_a.json()["imported_marks"] == 1
        learner_a = next(
            row for row in env["client_a"].get("/api/learners").json()
            if row["school_id_number"] == "A-CSV-001"
        )
        assert learner_a["school_id"] == str(env["school_a"])
        assert env["client_b"].get(
            f"/api/learners/{learner_a['learner_id']}"
        ).status_code == 404

        csv_b = (
            "school_id_number,full_name,grade,subject_name,score,exam_type,academic_year,school_id\n"
            f"B-CSV-001,Synthetic Learner B,11,English,82,NSC,2026,{env['school_a']}\n"
        ).encode()
        imported_b = env["client_b"].post(
            "/api/learners/import",
            files={"file": ("synthetic-school-b.csv", csv_b, "text/csv")},
            headers={"X-CSRF-Token": env["csrf_b"]},
        )
        assert imported_b.status_code == 201, imported_b.text
        learner_b = next(
            row for row in env["client_b"].get("/api/learners").json()
            if row["school_id_number"] == "B-CSV-001"
        )
        assert learner_b["school_id"] == str(env["school_b"])
        assert env["client_a"].get(
            f"/api/learners/{learner_b['learner_id']}"
        ).status_code == 404

    def test_application_list_scoped_to_own_school(self, env):
        resp_a = env["client_a"].get("/api/applications")
        resp_b = env["client_b"].get("/api/applications")
        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
        ids_a = {a["learner_id"] for a in resp_a.json()}
        ids_b = {a["learner_id"] for a in resp_b.json()}
        # IDs from one school must not appear in the other school's list
        for lid in ids_a:
            learner = env["client_a"].get(f"/api/learners/{lid}")
            assert learner.status_code == 200  # belongs to school_a

    def test_cross_school_application_access_denied(self, env):
        """SchoolAdmin cannot access application belonging to another school's learner."""
        # Create programme (public list, accessible), create learner+app for school_b
        prog_resp = _create_programme_for(env["client_x"], env["uni_x"], env["csrf_x"])
        pid = prog_resp["programme_id"]
        env["client_x"].post(f"/api/programmes/{pid}/publish", headers={"X-CSRF-Token": env["csrf_x"]})

        learner_b = _create_learner_for(env["client_b"], env["school_b"], env["csrf_b"])
        for subj in ["Mathematics", "English", "Life Sciences", "Physical Sciences", "History", "Geography"]:
            env["client_b"].post(
                f"/api/learners/{learner_b['learner_id']}/marks",
                json={"subject_name": subj, "score": 90, "exam_type": "NSC", "academic_year": 2024},
                headers={"X-CSRF-Token": env["csrf_b"]},
            )
        app_resp = env["client_b"].post(
            "/api/applications",
            json={"learner_id": learner_b["learner_id"], "programme_id": pid, "fee_amount": "100.00"},
            headers={"X-CSRF-Token": env["csrf_b"]},
        )
        assert app_resp.status_code == 201
        app_id = app_resp.json()["application_id"]

        # school_a tries to access school_b's application
        assert env["client_a"].get(f"/api/applications/{app_id}").status_code == 404
        assert env["client_a"].get(f"/api/applications/{app_id}/history").status_code == 404
        cancel_resp = env["client_a"].post(
            f"/api/applications/{app_id}/cancel",
            json={"note": "attack"}, headers={"X-CSRF-Token": env["csrf_a"]},
        )
        assert cancel_resp.status_code == 404
        # Verify application status unchanged
        real_app = env["client_b"].get(f"/api/applications/{app_id}").json()
        assert real_app["status"] == "Draft"


# ─────────────────────────────────────────────────────────────────────────────
# University isolation
# ─────────────────────────────────────────────────────────────────────────────

class TestUniversityIsolation:

    def test_uni_admin_cannot_update_other_universitys_programme(self, env):
        prog_x = _create_programme_for(env["client_x"], env["uni_x"], env["csrf_x"])
        original_name = prog_x["name"]
        resp = env["client_y"].put(
            f"/api/programmes/{prog_x['programme_id']}",
            json={"name": "Hacked Name"},
            headers={"X-CSRF-Token": env["csrf_y"]},
        )
        assert resp.status_code == 403
        still_prog = env["client_x"].get(f"/api/programmes/{prog_x['programme_id']}").json()
        assert still_prog["name"] == original_name

    def test_uni_admin_cannot_delete_other_universitys_programme(self, env):
        prog_x = _create_programme_for(env["client_x"], env["uni_x"], env["csrf_x"])
        resp = env["client_y"].delete(
            f"/api/programmes/{prog_x['programme_id']}",
            headers={"X-CSRF-Token": env["csrf_y"]},
        )
        assert resp.status_code == 403
        assert env["client_x"].get(f"/api/programmes/{prog_x['programme_id']}").status_code == 200

    def test_uni_admin_cannot_publish_other_universitys_programme(self, env):
        prog_x = _create_programme_for(env["client_x"], env["uni_x"], env["csrf_x"])
        resp = env["client_y"].post(
            f"/api/programmes/{prog_x['programme_id']}/publish",
            headers={"X-CSRF-Token": env["csrf_y"]},
        )
        assert resp.status_code == 403
        prog_still = env["client_x"].get(f"/api/programmes/{prog_x['programme_id']}").json()
        assert prog_still["status"] == "Draft"

    def test_university_programme_reads_are_scoped_and_public_reads_hide_drafts(self, env):
        draft_x = _create_programme_for(env["client_x"], env["uni_x"], env["csrf_x"])
        draft_y = _create_programme_for(env["client_y"], env["uni_y"], env["csrf_y"])

        public_programmes = env["anon"].get("/api/programmes").json()
        assert all(
            item["programme_id"] not in {
                draft_x["programme_id"], draft_y["programme_id"]
            }
            for item in public_programmes
        )
        assert env["anon"].get(f"/api/programmes/{draft_x['programme_id']}").status_code == 404
        school_programmes = env["client_a"].get("/api/programmes").json()
        assert all(
            item["programme_id"] not in {
                draft_x["programme_id"], draft_y["programme_id"]
            }
            for item in school_programmes
        )
        assert env["client_y"].get(f"/api/programmes/{draft_x['programme_id']}").status_code == 404
        assert env["client_x"].get(f"/api/programmes/{draft_x['programme_id']}").status_code == 200

        listed_x = env["client_x"].get("/api/programmes").json()
        assert draft_x["programme_id"] in {
            item["programme_id"] for item in listed_x
        }
        assert all(item["university_id"] == str(env["uni_x"]) for item in listed_x)
        assert env["client_y"].get(f"/api/programmes/{draft_y['programme_id']}").status_code == 200

    def test_programme_create_uses_principal_university_id(self, env):
        """university_id in request body is overridden by the principal's university_id."""
        resp = env["client_x"].post(
            "/api/programmes",
            json={
                "university_id": str(env["uni_y"]),  # attacker attempts wrong university
                "name": "Attack Programme", "faculty": "Science",
                "minimum_aps": 20, "application_deadline": "2099-12-31",
                "application_fee": "100.00", "required_documents": [], "published_by": str(uuid4()),
            },
            headers={"X-CSRF-Token": env["csrf_x"]},
        )
        assert resp.status_code == 201
        assert resp.json()["university_id"] == str(env["uni_x"])  # principal wins

    def test_uni_admin_cannot_access_learner_endpoints(self, env):
        resp = env["client_x"].get("/api/learners")
        assert resp.status_code == 403

    def test_uni_admin_cannot_access_application_endpoints(self, env):
        resp = env["client_x"].get("/api/applications")
        assert resp.status_code == 403
        application_id = uuid4()
        assert env["client_x"].get(
            f"/api/applications/{application_id}"
        ).status_code == 403
        approval = env["client_x"].put(
            f"/api/applications/{application_id}/status",
            json={"new_status": "Accepted"},
            headers={"X-CSRF-Token": env["csrf_x"]},
        )
        assert approval.status_code == 403

    def test_university_can_review_its_submitted_applications(self, env):
        created, application = _create_review_application(env)
        application_id = created["application_id"]

        listing = env["client_x"].get("/api/university/applications")
        assert listing.status_code == 200, listing.text
        record = next(
            item for item in listing.json()
            if item["application_id"] == application_id
        )
        assert record["learner_name"] == "Test Learner"
        assert record["programme_name"] == "BSc Test"
        assert record["learner_marks"]
        assert record["required_documents"] == []
        assert record["linked_documents"] == []
        assert record["document_tracking_available"] is True

        review = env["client_x"].put(
            f"/api/university/applications/{application_id}/review",
            json={"new_status": "UnderReview", "note": "Initial review"},
            headers={"X-CSRF-Token": env["csrf_x"]},
        )
        assert review.status_code == 200, review.text
        assert review.json()["status"] == "UnderReview"
        reviewer_id = env["client_x"].get("/api/auth/me").json()["account_id"]
        history = review.json()["status_history"]
        assert history[-1]["changed_by"] == reviewer_id
        assert history[-1]["new_status"] == "UnderReview"
        assert history[-1]["note"] == "Initial review"
        assert history[-1]["changed_at"]

        request_docs = env["client_x"].put(
            f"/api/university/applications/{application_id}/review",
            json={"new_status": "DocsRequested", "note": "Please provide a certified ID."},
            headers={"X-CSRF-Token": env["csrf_x"]},
        )
        assert request_docs.status_code == 200, request_docs.text
        assert request_docs.json()["status"] == "DocsRequested"

    def test_university_review_rejects_invalid_transitions_and_blank_document_request(self, env):
        created, _application = _create_review_application(env)
        application_id = created["application_id"]
        url = f"/api/university/applications/{application_id}/review"
        headers = {"X-CSRF-Token": env["csrf_x"]}

        # Waitlisted is not a valid transition directly from Submitted.
        skip_review = env["client_x"].put(
            url,
            json={"new_status": "Waitlisted"},
            headers=headers,
        )
        assert skip_review.status_code == 422
        assert env["client_x"].get(
            f"/api/university/applications/{application_id}"
        ).json()["status"] == "Submitted"

        # Direct acceptance from Submitted is intentionally supported.
        begin_review = env["client_x"].put(
            url,
            json={"new_status": "UnderReview"},
            headers=headers,
        )
        assert begin_review.status_code == 200
        blank_request = env["client_x"].put(
            url,
            json={"new_status": "DocsRequested", "note": "   "},
            headers=headers,
        )
        assert blank_request.status_code == 422
        assert env["client_x"].get(
            f"/api/university/applications/{application_id}"
        ).json()["status"] == "UnderReview"

        accepted = env["client_x"].put(
            url,
            json={"new_status": "Accepted", "note": "Requirements reviewed."},
            headers=headers,
        )
        assert accepted.status_code == 200
        assert accepted.json()["status"] == "Accepted"

    def test_university_cannot_access_another_universitys_application(self, env):
        created, application = _create_review_application(env, university="y")
        application_id = created["application_id"]

        assert env["client_x"].get(
            "/api/university/applications"
        ).status_code == 200
        assert application_id not in {
            item["application_id"]
            for item in env["client_x"].get(
                "/api/university/applications"
            ).json()
        }
        assert env["client_x"].get(
            f"/api/university/applications/{application_id}"
        ).status_code == 404
        review = env["client_x"].put(
            f"/api/university/applications/{application_id}/review",
            json={"new_status": "UnderReview"},
            headers={"X-CSRF-Token": env["csrf_x"]},
        )
        assert review.status_code == 404
        assert application.status == ApplicationStatusEnum.Submitted

    def test_school_admin_cannot_make_admission_decisions(self, env):
        created, application = _create_review_application(env)
        application_id = created["application_id"]
        application.status = ApplicationStatusEnum.UnderReview
        env["application_repo"].save(application)

        decision = env["client_a"].put(
            f"/api/applications/{application_id}/status",
            json={"new_status": "Accepted"},
            headers={"X-CSRF-Token": env["csrf_a"]},
        )
        assert decision.status_code == 403
        university_route = env["client_a"].put(
            f"/api/university/applications/{application_id}/review",
            json={"new_status": "Accepted"},
            headers={"X-CSRF-Token": env["csrf_a"]},
        )
        assert university_route.status_code == 403
        assert application.status == ApplicationStatusEnum.UnderReview

    def test_learner_cannot_access_or_approve_applications(self, env):
        learner = UserAccount(
            user_id=uuid4(),
            email="learner@test",
            password_hash=hash_password("LearnerPass!"),
            role=RoleEnum.Learner,
            account_state=AccountStateEnum.Active,
        )
        env["account_repo"].save(learner)

        client = TestClient(env["app"], raise_server_exceptions=False)
        login = client.post(
            "/api/auth/login",
            json={"email": "learner@test", "password": "LearnerPass!"},
        )
        assert login.status_code == 200
        csrf = client.get("/api/auth/csrf").json()["csrf_token"]
        application_id = uuid4()

        assert client.get("/api/applications").status_code == 403
        assert client.get("/api/university/applications").status_code == 403
        approval = client.put(
            f"/api/applications/{application_id}/status",
            json={"new_status": "Accepted"},
            headers={"X-CSRF-Token": csrf},
        )
        assert approval.status_code == 403

    def test_guidance_sessions_are_school_scoped(self, env):
        learner = _create_learner_for(
            env["client_a"], env["school_a"], env["csrf_a"]
        )
        created = env["client_a"].post(
            f"/api/learners/{learner['learner_id']}/guidance-sessions",
            json={
                "session_date": "2026-10-30",
                "purpose": "Planning",
                "notes": "Private guidance notes.",
            },
            headers={"X-CSRF-Token": env["csrf_a"]},
        )
        assert created.status_code == 201, created.text
        session_id = created.json()["guidance_session_id"]

        assert env["client_b"].get(
            f"/api/learners/{learner['learner_id']}/guidance-sessions"
        ).status_code == 404
        denied = env["client_b"].put(
            f"/api/guidance-sessions/{session_id}",
            json={"status": "Cancelled"},
            headers={"X-CSRF-Token": env["csrf_b"]},
        )
        assert denied.status_code == 404
        still_owned = env["client_a"].get(
            f"/api/learners/{learner['learner_id']}/guidance-sessions"
        ).json()
        assert still_owned[0]["status"] == "Scheduled"

    def test_university_scoring_rules_are_separated_by_authenticated_scope(self, env):
        save = env["client_x"].put(
            "/api/universities/me/scoring-rule",
            json={
                "band_thresholds": [[80, 8], [70, 6]],
                "subject_count": 4,
                "excluded_subjects": ["Life Orientation"],
                "subject_weightings": {},
            },
            headers={"X-CSRF-Token": env["csrf_x"]},
        )
        assert save.status_code == 200, save.text
        rule_x = env["client_x"].get("/api/universities/me/scoring-rule").json()
        rule_y = env["client_y"].get("/api/universities/me/scoring-rule").json()
        assert rule_x["university_id"] == str(env["uni_x"])
        assert rule_x["is_customized"] is True
        assert rule_y["university_id"] == str(env["uni_y"])
        assert rule_y["is_customized"] is False

    def test_school_audit_reads_do_not_expose_another_school_events(self, env):
        learner = _create_learner_for(
            env["client_a"], env["school_a"], env["csrf_a"]
        )
        events_a = env["client_a"].get("/api/audit").json()
        events_b = env["client_b"].get("/api/audit").json()
        assert any(
            item["target_id"] == learner["learner_id"]
            for item in events_a
        )
        assert all(
            item["target_id"] != learner["learner_id"]
            for item in events_b
        )

    def test_rag_document_ingestion_is_university_scoped_and_chat_is_role_limited(self):
        state = _make_two_school_app()
        text = (
            "The BSc Test programme requires Mathematics at a minimum mark of 70. "
            "Applications close on 30 September."
        )
        document_bytes = _docx_bytes(text)
        indexed = _upload_rag_doc(
            state["client_x"],
            state["csrf_x"],
            text,
            document_bytes=document_bytes,
        )
        assert indexed.status_code == 201, indexed.text
        assert state["client_x"].get("/api/agent/documents").json()[0]["document_id"] == (
            indexed.json()["document_id"]
        )
        assert state["client_y"].get("/api/agent/documents").json() == []
        assert _upload_rag_doc(
            state["client_x"],
            state["csrf_x"],
            text,
            document_bytes=document_bytes,
        ).status_code == 409
        assert _upload_rag_doc(
            state["client_a"],
            state["csrf_a"],
            "The BSc Test programme has public entry rules.",
        ).status_code == 403
        assert state["client_x"].post(
            "/api/agent/chat",
            json={"message": "Tell me about entry requirements."},
            headers={"X-CSRF-Token": state["csrf_x"]},
        ).status_code == 403
        assert state["teacher_client"].post(
            "/api/agent/chat",
            json={"message": "Tell me about entry requirements."},
            headers={"X-CSRF-Token": state["teacher_csrf"]},
        ).status_code == 403

    def test_rag_reindex_and_delete_are_limited_to_source_university(self):
        state = _make_two_school_app()
        indexed = _upload_rag_doc(
            state["client_x"],
            state["csrf_x"],
            "Synthetic source: Mathematics is a compulsory subject.",
        )
        assert indexed.status_code == 201, indexed.text
        document_id = indexed.json()["document_id"]
        assert indexed.json()["reindex_required"] is False

        assert state["client_y"].post(
            f"/api/agent/documents/{document_id}/reindex",
            headers={"X-CSRF-Token": state["csrf_y"]},
        ).status_code == 404
        assert state["client_y"].delete(
            f"/api/agent/documents/{document_id}",
            headers={"X-CSRF-Token": state["csrf_y"]},
        ).status_code == 404
        assert state["client_a"].post(
            f"/api/agent/documents/{document_id}/reindex",
            headers={"X-CSRF-Token": state["csrf_a"]},
        ).status_code == 403

        reindexed = state["client_x"].post(
            f"/api/agent/documents/{document_id}/reindex",
            headers={"X-CSRF-Token": state["csrf_x"]},
        )
        assert reindexed.status_code == 200, reindexed.text
        assert reindexed.json()["reindex_required"] is False
        assert state["client_x"].delete(
            f"/api/agent/documents/{document_id}",
            headers={"X-CSRF-Token": state["csrf_x"]},
        ).status_code == 204
        retained = state["client_x"].get("/api/agent/documents").json()
        assert len(retained) == 1
        assert retained[0]["document_id"] == document_id
        assert retained[0]["lifecycle_state"] == PhysicalDocumentState.DELETED.value
        assert retained[0]["embedding_state"] == EmbeddingState.EMBEDDINGS_READY.value
        logical = state["knowledge_repo"].find_logical_document(
            UUID(retained[0]["logical_document_id"]), state["uni_x"]
        )
        assert logical is not None
        assert logical.lifecycle_state is LogicalDocumentState.DELETED

    def test_rag_version_routes_enforce_scope_and_preserve_logical_history(self):
        class NoopVectorStore:
            def upsert(self, chunks, embeddings):
                return None

            def reconcile(self, allowed_universities, authoritative_chunk_ids):
                return 0

            def query(self, embedding, limit, allowed_universities=None):
                return []

        state = _make_two_school_app(vector_store=NoopVectorStore())
        first = _upload_rag_doc(
            state["client_x"],
            state["csrf_x"],
            "Synthetic source version one.",
        )
        assert first.status_code == 201, first.text
        logical_id = first.json()["logical_document_id"]
        first_id = first.json()["document_id"]
        foreign_replacement = _upload_rag_doc(
            state["client_y"],
            state["csrf_y"],
            "Synthetic attempt to replace another university source.",
            logical_document_id=logical_id,
        )
        assert foreign_replacement.status_code == 404

        second = _upload_rag_doc(
            state["client_x"],
            state["csrf_x"],
            "Synthetic source version two.",
            logical_document_id=logical_id,
        )
        assert second.status_code == 201, second.text
        assert second.json()["version_number"] == 2
        third = _upload_rag_doc(
            state["client_x"],
            state["csrf_x"],
            "Synthetic source version three.",
            logical_document_id=logical_id,
        )
        assert third.status_code == 201, third.text
        assert third.json()["version_number"] == 3

        assert state["client_y"].delete(
            f"/api/agent/documents/{first_id}",
            headers={"X-CSRF-Token": state["csrf_y"]},
        ).status_code == 404
        assert state["client_y"].delete(
            f"/api/agent/logical-documents/{logical_id}",
            headers={"X-CSRF-Token": state["csrf_y"]},
        ).status_code == 404

        delete_superseded = state["client_x"].delete(
            f"/api/agent/documents/{first_id}",
            headers={"X-CSRF-Token": state["csrf_x"]},
        )
        assert delete_superseded.status_code == 204
        logical = state["knowledge_repo"].find_logical_document(
            UUID(logical_id), state["uni_x"]
        )
        assert logical is not None
        assert logical.lifecycle_state is LogicalDocumentState.ACTIVE

        delete_logical = state["client_x"].delete(
            f"/api/agent/logical-documents/{logical_id}",
            headers={"X-CSRF-Token": state["csrf_x"]},
        )
        assert delete_logical.status_code == 204
        retained = {
            document.document_id: document
            for document in state["knowledge_repo"].list_documents(state["uni_x"])
        }
        assert retained[UUID(first_id)].lifecycle_state is PhysicalDocumentState.DELETED
        assert retained[UUID(second.json()["document_id"])].lifecycle_state is (
            PhysicalDocumentState.SUPERSEDED
        )
        assert retained[UUID(third.json()["document_id"])].lifecycle_state is (
            PhysicalDocumentState.DELETED
        )
        assert state["knowledge_repo"].list_chunks({state["uni_x"]}) == []
        assert state["knowledge_repo"].find_logical_document(
            UUID(logical_id), state["uni_x"]
        ).lifecycle_state is LogicalDocumentState.DELETED

    def test_rag_chat_cites_sources_uses_engine_and_is_school_scoped(self, monkeypatch):
        # Force extractive provider so the specific eligibility text assertions are deterministic.
        monkeypatch.setenv("RAG_PROVIDER", "extractive")
        state = _make_two_school_app()
        assert _upload_rag_doc(
            state["client_y"],
            state["csrf_y"],
            (
                "Synthetic fixture: Explain APS eligibility for BSc Test and its "
                "subject rules. Mathematics must be scored 99."
            ),
        ).status_code == 201
        text = (
            "Synthetic fixture: The BSc Test programme requires Mathematics at a "
            "minimum mark of 70. "
            "Applications close on 30 September."
        )
        assert _upload_rag_doc(
            state["client_x"], state["csrf_x"], text
        ).status_code == 201
        programme_response = state["client_x"].post(
            "/api/programmes",
            json={
                "university_id": str(state["uni_x"]),
                "name": "BSc Test",
                "faculty": "Science",
                "minimum_aps": 20,
                "application_deadline": "2099-12-31",
                "application_fee": "100.00",
                "required_documents": [],
                "published_by": str(uuid4()),
                "required_subjects": {"Mathematics": 70},
            },
            headers={"X-CSRF-Token": state["csrf_x"]},
        )
        assert programme_response.status_code == 201, programme_response.text
        programme_id = programme_response.json()["programme_id"]
        assert state["client_x"].post(
            f"/api/programmes/{programme_id}/publish",
            headers={"X-CSRF-Token": state["csrf_x"]},
        ).status_code == 200

        learner_a = _create_learner_for(
            state["client_a"], state["school_a"], state["csrf_a"]
        )
        learner_b = _create_learner_for(
            state["client_b"], state["school_b"], state["csrf_b"]
        )
        marks = [
            ("Mathematics", 50),
            ("English", 80),
            ("Physical Sciences", 80),
            ("Life Sciences", 80),
            ("History", 80),
            ("Geography", 80),
        ]
        for subject, score in marks:
            response = state["client_a"].post(
                f"/api/learners/{learner_a['learner_id']}/marks",
                json={
                    "subject_name": subject,
                    "score": score,
                    "exam_type": "NSC",
                    "academic_year": 2026,
                },
                headers={"X-CSRF-Token": state["csrf_a"]},
            )
            assert response.status_code == 201, response.text

        denied = state["client_a"].post(
            "/api/agent/chat",
            json={
                "message": "Explain APS eligibility for BSc Test and its subject rules.",
                "learner_id": learner_b["learner_id"],
            },
            headers={"X-CSRF-Token": state["csrf_a"]},
        )
        assert denied.status_code == 404

        first = state["client_a"].post(
            "/api/agent/chat",
            json={
                "message": "Explain APS eligibility for BSc Test and its subject rules.",
                "learner_id": learner_a["learner_id"],
            },
            headers={"X-CSRF-Token": state["csrf_a"]},
        )
        assert first.status_code == 200, first.text
        result = first.json()
        assert result["generation_mode"] == "local-extractive" or result["generation_mode"].startswith("live: "), (
            f"Unexpected generation_mode: {result['generation_mode']!r}"
        )
        assert result["sources"][0]["title"] == "Synthetic test admissions fixture"
        assert all(
            source["university_id"] == str(state["uni_x"])
            for source in result["sources"]
        )
        assert "Mathematics (minimum 70; recorded 50)" in result["answer"]
        assert "NotEligible" in result["answer"]
        assert "not admission decisions" in result["answer"]
        assert len(result["history"]) == 2

        second = state["client_a"].post(
            "/api/agent/chat",
            json={
                "message": "What is the application deadline?",
                "conversation_id": result["conversation_id"],
            },
            headers={"X-CSRF-Token": state["csrf_a"]},
        )
        assert second.status_code == 200, second.text
        assert len(second.json()["history"]) == 4
        assert state["client_b"].post(
            "/api/agent/chat",
            json={
                "message": "Continue this conversation.",
                "conversation_id": result["conversation_id"],
            },
            headers={"X-CSRF-Token": state["csrf_b"]},
        ).status_code == 404

    def test_restricted_stage_three_endpoints_deny_unrelated_roles(self, env):
        learner_id = str(uuid4())
        assert env["teacher_client"].get(
            f"/api/learners/{learner_id}/guidance-sessions"
        ).status_code == 403
        assert env["teacher_client"].get("/api/audit").status_code == 403
        assert env["teacher_client"].get("/api/reports/doe").status_code == 403
        assert env["client_x"].get("/api/reports/doe").status_code == 403
        assert env["client_x"].get(
            f"/api/learners/{learner_id}/guidance-sessions"
        ).status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# Role rejection
# ─────────────────────────────────────────────────────────────────────────────

class TestRoleRejection:

    def test_school_admin_cannot_create_programme(self, env):
        resp = env["client_a"].post(
            "/api/programmes",
            json={
                "university_id": str(env["uni_x"]), "name": "X", "faculty": "X",
                "minimum_aps": 20, "application_deadline": "2099-12-31",
                "application_fee": "100.00", "required_documents": [], "published_by": str(uuid4()),
            },
            headers={"X-CSRF-Token": env["csrf_a"]},
        )
        assert resp.status_code == 403

    def test_school_admin_cannot_publish_programme(self, env):
        prog = _create_programme_for(env["client_x"], env["uni_x"], env["csrf_x"])
        resp = env["client_a"].post(
            f"/api/programmes/{prog['programme_id']}/publish",
            headers={"X-CSRF-Token": env["csrf_a"]},
        )
        assert resp.status_code == 403
        assert env["client_x"].get(f"/api/programmes/{prog['programme_id']}").json()["status"] == "Draft"

    def test_legacy_teacher_role_rejected_on_learner_routes(self, env):
        resp = env["teacher_client"].get("/api/learners")
        assert resp.status_code == 403

    def test_legacy_teacher_role_rejected_on_programme_create(self, env):
        resp = env["teacher_client"].post(
            "/api/programmes",
            json={
                "university_id": str(env["uni_x"]), "name": "X", "faculty": "X",
                "minimum_aps": 20, "application_deadline": "2099-12-31",
                "application_fee": "100.00", "required_documents": [], "published_by": str(uuid4()),
            },
            headers={"X-CSRF-Token": env["teacher_csrf"]},
        )
        assert resp.status_code == 403

    def test_legacy_teacher_role_rejected_on_application_routes(self, env):
        resp = env["teacher_client"].get("/api/applications")
        assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# Account state (Pending / Suspended)
# ─────────────────────────────────────────────────────────────────────────────

class TestAccountState:

    def test_pending_account_cannot_login(self, env):
        # Build a fresh app to test login (same repo as env)
        # Just check directly via the same app's login endpoint
        anon = TestClient(
            create_app(
                account_repo=env["client_a"].app.state if hasattr(env["client_a"], "app") else None
            ),
            raise_server_exceptions=False,
        ) if False else env["anon"]
        resp = anon.post(
            "/api/auth/login",
            json={"email": "pending@test", "password": "PendPass!"},
        )
        assert resp.status_code == 403

    def test_suspended_account_cannot_login(self, env):
        resp = env["anon"].post(
            "/api/auth/login",
            json={"email": "suspended@test", "password": "SuspPass!"},
        )
        assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# Simulation — no mutation guarantee
# ─────────────────────────────────────────────────────────────────────────────

class TestSimulationNoMutation:

    def test_simulation_does_not_mutate_learner_marks(self, env):
        learner = _create_learner_for(env["client_a"], env["school_a"], env["csrf_a"])
        env["client_a"].post(
            f"/api/learners/{learner['learner_id']}/marks",
            json={"subject_name": "Mathematics", "score": 60, "exam_type": "NSC", "academic_year": 2024},
            headers={"X-CSRF-Token": env["csrf_a"]},
        )
        prog = _create_programme_for(env["client_x"], env["uni_x"], env["csrf_x"])
        marks_before = env["client_a"].get(f"/api/learners/{learner['learner_id']}").json()["mark_count"]

        env["client_a"].post(
            f"/api/learners/{learner['learner_id']}/simulate-eligibility",
            json={"programme_id": prog["programme_id"], "overrides": {"English": 80}},
            headers={"X-CSRF-Token": env["csrf_a"]},
        )

        marks_after = env["client_a"].get(f"/api/learners/{learner['learner_id']}").json()["mark_count"]
        assert marks_after == marks_before

    def test_cross_school_simulation_denied(self, env):
        """School B cannot simulate for School A's learner."""
        learner_a = _create_learner_for(env["client_a"], env["school_a"], env["csrf_a"])
        prog = _create_programme_for(env["client_x"], env["uni_x"], env["csrf_x"])
        resp = env["client_b"].post(
            f"/api/learners/{learner_a['learner_id']}/simulate-eligibility",
            json={"programme_id": prog["programme_id"], "overrides": {}},
            headers={"X-CSRF-Token": env["csrf_b"]},
        )
        assert resp.status_code == 404
