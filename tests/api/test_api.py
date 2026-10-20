"""
tests/api/test_api.py
======================
Integration tests for the UniMatch REST API.

Uses FastAPI's built-in TestClient to exercise all endpoints end-to-end
through the full stack: API → Service → In-Memory Repository.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from unimatch.api import create_app
from unimatch.entities import NSC_DEFAULT_SCORING_RULE, ScoringRule
from unimatch.repositories.inmemory import InMemoryScoringRuleRepository


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """A fresh TestClient backed by fresh in-memory repos."""
    return TestClient(create_app())


# ── Constants ─────────────────────────────────────────────────────────────────

COUNSELOR_ID = str(uuid4())
SCHOOL_ID = str(uuid4())
UNIVERSITY_ID = str(uuid4())
PUBLISHER_ID = str(uuid4())
ACTOR_ID = str(uuid4())
FAR_FUTURE = "2099-12-31"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _create_learner(client: TestClient) -> dict:
    resp = client.post("/api/learners", json={
        "full_name": "Thabo Nkosi",
        "school_id_number": "SCH-001",
        "grade": 12,
        "counselor_id": COUNSELOR_ID,
        "school_id": SCHOOL_ID,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_programme(
    client: TestClient,
    deadline: str = FAR_FUTURE,
    aps: int = 28,
    required_subjects: dict | None = None,
) -> dict:
    body = {
        "university_id": UNIVERSITY_ID,
        "name": "BSc Computer Science",
        "faculty": "Science",
        "minimum_aps": aps,
        "application_deadline": deadline,
        "application_fee": "200.00",
        "required_documents": ["ID", "Matric Certificate"],
        "published_by": PUBLISHER_ID,
    }
    if required_subjects is not None:
        body["required_subjects"] = required_subjects
    resp = client.post("/api/programmes", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _publish_programme(client: TestClient, pid: str) -> dict:
    resp = client.post(f"/api/programmes/{pid}/publish")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _create_and_publish_programme(
    client: TestClient,
    aps: int = 28,
    required_subjects: dict | None = None,
) -> dict:
    prog = _create_programme(client, aps=aps, required_subjects=required_subjects)
    return _publish_programme(client, prog["programme_id"])


def _add_marks_via_api(client: TestClient, learner_id: str, score: int = 90) -> None:
    """Add 6 generic subject marks to a learner via the API (for eligibility)."""
    subjects = ["Mathematics", "English", "Life Sciences", "Physical Sciences", "History", "Geography"]
    for subj in subjects:
        resp = client.post(f"/api/learners/{learner_id}/marks", json={
            "subject_name": subj, "score": score, "exam_type": "NSC", "academic_year": 2024,
        })
        assert resp.status_code == 201, resp.text


def _create_eligible_learner(client: TestClient) -> dict:
    """Create a learner and add marks that give Guaranteed eligibility (APS 42, min 28)."""
    learner = _create_learner(client)
    _add_marks_via_api(client, learner["learner_id"])
    return learner


def _create_application(client: TestClient, learner_id: str, programme_id: str) -> dict:
    resp = client.post("/api/applications", json={
        "learner_id": learner_id,
        "programme_id": programme_id,
        "fee_amount": "200.00",
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


# ─────────────────────────────────────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_check(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ─────────────────────────────────────────────────────────────────────────────
# Learner endpoints
# ─────────────────────────────────────────────────────────────────────────────

class TestLearnerEndpoints:

    def test_create_learner(self, client):
        learner = _create_learner(client)
        assert learner["full_name"] == "Thabo Nkosi"
        assert learner["grade"] == 12
        assert "learner_id" in learner

    def test_get_learner(self, client):
        learner = _create_learner(client)
        resp = client.get(f"/api/learners/{learner['learner_id']}")
        assert resp.status_code == 200
        assert resp.json()["learner_id"] == learner["learner_id"]

    def test_get_nonexistent_learner_404(self, client):
        resp = client.get(f"/api/learners/{uuid4()}")
        assert resp.status_code == 404

    def test_list_learners(self, client):
        _create_learner(client)
        resp = client.get("/api/learners")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert len(resp.json()) >= 1

    def test_update_learner(self, client):
        learner = _create_learner(client)
        resp = client.put(f"/api/learners/{learner['learner_id']}", json={"full_name": "Sipho Dlamini"})
        assert resp.status_code == 200
        assert resp.json()["full_name"] == "Sipho Dlamini"

    def test_delete_learner(self, client):
        learner = _create_learner(client)
        resp = client.delete(f"/api/learners/{learner['learner_id']}")
        assert resp.status_code == 204
        assert client.get(f"/api/learners/{learner['learner_id']}").status_code == 404

    def test_add_mark(self, client):
        learner = _create_learner(client)
        resp = client.post(f"/api/learners/{learner['learner_id']}/marks", json={
            "subject_name": "Mathematics",
            "score": 80,
            "exam_type": "NSC",
            "academic_year": 2024,
        })
        assert resp.status_code == 201
        assert resp.json()["mark_count"] == 1

    def test_add_invalid_mark_422(self, client):
        learner = _create_learner(client)
        resp = client.post(f"/api/learners/{learner['learner_id']}/marks", json={
            "subject_name": "Mathematics",
            "score": 150,
            "exam_type": "NSC",
            "academic_year": 2024,
        })
        assert resp.status_code == 422

    def test_get_aps_score(self, client):
        learner = _create_learner(client)
        client.post(f"/api/learners/{learner['learner_id']}/marks", json={
            "subject_name": "Mathematics", "score": 80, "exam_type": "NSC", "academic_year": 2024,
        })
        resp = client.get(f"/api/learners/{learner['learner_id']}/aps")
        assert resp.status_code == 200
        assert resp.json()["aps_score"] == 7

    def test_deactivate_learner(self, client):
        learner = _create_learner(client)
        resp = client.post(f"/api/learners/{learner['learner_id']}/deactivate")
        assert resp.status_code == 200
        assert resp.json()["status"] == "Inactive"


# ─────────────────────────────────────────────────────────────────────────────
# Per-university APS scoring API tests (REQ-002)
#
# All ScoringRule instances below are SYNTHETIC test rules. They do not
# represent official admission rules of any South African university.
# ─────────────────────────────────────────────────────────────────────────────

class TestPerUniversityAps:

    @pytest.fixture(scope="class")
    def client_with_rule(self):
        """A fresh TestClient with a synthetic ScoringRule pre-registered.

        Returns a dict with keys 'client' and 'university_id'.

        The synthetic rule (NOT an official university rule):
          - Weights Mathematics by 2.0 (all other subjects 1.0).
          - Excludes 'Life Orientation' from the count.
          - Uses standard NSC bands and top-6 count.

        Learner with Maths 80, English 70, LO 50 (added in each test):
          - Default NSC formula:  7 + 6 + 4 = 17
          - With this rule:  floor(7*2.0) + 6 = 14 + 6 = 20  (LO excluded)
        """
        repo = InMemoryScoringRuleRepository()
        synthetic_uni_id = uuid4()
        rule = ScoringRule(
            university_id=synthetic_uni_id,
            band_thresholds=NSC_DEFAULT_SCORING_RULE.band_thresholds,
            subject_count=6,
            excluded_subjects=["Life Orientation"],
            subject_weightings={"Mathematics": 2.0},
        )
        repo.save(rule)
        return {
            "client": TestClient(create_app(scoring_rule_repo=repo)),
            "university_id": synthetic_uni_id,
        }

    def _setup_learner_with_marks(self, client: TestClient) -> str:
        """Create a learner and add three marks; return learner_id."""
        resp = client.post("/api/learners", json={
            "full_name": "Naledi Dlamini",
            "school_id_number": "SRU-001",
            "grade": 12,
            "counselor_id": str(uuid4()),
            "school_id": str(uuid4()),
        })
        assert resp.status_code == 201
        lid = resp.json()["learner_id"]
        for subj, score in [("Mathematics", 80), ("English", 70), ("Life Orientation", 50)]:
            r = client.post(f"/api/learners/{lid}/marks", json={
                "subject_name": subj, "score": score, "exam_type": "NSC", "academic_year": 2025,
            })
            assert r.status_code == 201
        return lid

    def test_aps_without_university_id_uses_default_formula(self, client_with_rule):
        """Omitting university_id returns the standard NSC APS and university_id=null."""
        client = client_with_rule["client"]
        lid = self._setup_learner_with_marks(client)
        resp = client.get(f"/api/learners/{lid}/aps")
        assert resp.status_code == 200
        body = resp.json()
        assert body["aps_score"] == 17  # 7+6+4 = 17 (LO included, no weighting)
        assert body["university_id"] is None

    def test_aps_with_registered_rule_applies_weighting_and_exclusion(self, client_with_rule):
        """university_id for a registered synthetic rule returns the rule-specific APS
        and echoes the university_id in the response."""
        client = client_with_rule["client"]
        uid = str(client_with_rule["university_id"])
        lid = self._setup_learner_with_marks(client)
        resp = client.get(f"/api/learners/{lid}/aps", params={"university_id": uid})
        assert resp.status_code == 200
        body = resp.json()
        # Maths 7*2=14, English 6; LO excluded; floor(14+6)=20
        assert body["aps_score"] == 20
        assert body["university_id"] == uid

    def test_aps_with_registered_rule_differs_from_default(self, client_with_rule):
        """The university-specific APS must differ from the standard NSC APS
        for a learner whose marks are affected by the rule."""
        client = client_with_rule["client"]
        uid = str(client_with_rule["university_id"])
        lid = self._setup_learner_with_marks(client)
        default_aps = client.get(f"/api/learners/{lid}/aps").json()["aps_score"]
        rule_aps = client.get(
            f"/api/learners/{lid}/aps", params={"university_id": uid}
        ).json()["aps_score"]
        assert default_aps != rule_aps

    def test_aps_unknown_university_falls_back_silently_with_null_id(self, client_with_rule):
        """A university_id with no registered rule must fall back to the standard
        NSC formula. The response must return university_id=null to signal that
        no university-specific formula was applied."""
        client = client_with_rule["client"]
        lid = self._setup_learner_with_marks(client)
        resp = client.get(
            f"/api/learners/{lid}/aps",
            params={"university_id": str(uuid4())},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["aps_score"] == 17  # standard NSC formula (17 = 7+6+4)
        # CRITICAL: must not echo the requested university_id when the default was used
        assert body["university_id"] is None, (
            "Response must return university_id=null when no rule is registered "
            "to avoid implying a university-specific formula was applied."
        )

    def test_aps_unknown_university_matches_no_university_id(self, client_with_rule):
        """The APS produced when an unregistered university_id is supplied must
        equal the APS produced when no university_id is supplied at all."""
        client = client_with_rule["client"]
        lid = self._setup_learner_with_marks(client)
        default = client.get(f"/api/learners/{lid}/aps").json()["aps_score"]
        fallback = client.get(
            f"/api/learners/{lid}/aps",
            params={"university_id": str(uuid4())},
        ).json()["aps_score"]
        assert default == fallback


# ─────────────────────────────────────────────────────────────────────────────
# Programme endpoints
# ─────────────────────────────────────────────────────────────────────────────

class TestProgrammeEndpoints:

    def test_create_programme(self, client):
        prog = _create_programme(client)
        assert prog["name"] == "BSc Computer Science"
        assert prog["status"] == "Draft"

    def test_get_programme(self, client):
        prog = _create_programme(client)
        resp = client.get(f"/api/programmes/{prog['programme_id']}")
        assert resp.status_code == 200

    def test_get_nonexistent_programme_404(self, client):
        resp = client.get(f"/api/programmes/{uuid4()}")
        assert resp.status_code == 404

    def test_list_programmes(self, client):
        _create_programme(client)
        resp = client.get("/api/programmes")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_list_published_only(self, client):
        prog = _create_and_publish_programme(client)
        resp = client.get("/api/programmes?published_only=true")
        ids = [p["programme_id"] for p in resp.json()]
        assert prog["programme_id"] in ids
        for p in resp.json():
            assert p["is_active"] is True

    def test_update_programme(self, client):
        prog = _create_programme(client)
        resp = client.put(f"/api/programmes/{prog['programme_id']}", json={"name": "BSc Data Science"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "BSc Data Science"

    def test_delete_programme(self, client):
        prog = _create_programme(client)
        assert client.delete(f"/api/programmes/{prog['programme_id']}").status_code == 204
        assert client.get(f"/api/programmes/{prog['programme_id']}").status_code == 404

    def test_publish_programme(self, client):
        prog = _create_programme(client)
        resp = client.post(f"/api/programmes/{prog['programme_id']}/publish")
        assert resp.status_code == 200
        assert resp.json()["status"] == "Published"

    def test_publish_expired_programme_400(self, client):
        prog = _create_programme(client, deadline="2000-01-01")
        resp = client.post(f"/api/programmes/{prog['programme_id']}/publish")
        assert resp.status_code == 400

    def test_deactivate_programme(self, client):
        prog = _create_and_publish_programme(client)
        resp = client.post(f"/api/programmes/{prog['programme_id']}/deactivate")
        assert resp.status_code == 200
        assert resp.json()["status"] == "Deactivated"

    def test_extend_deadline(self, client):
        prog = _create_programme(client)
        resp = client.post(f"/api/programmes/{prog['programme_id']}/extend-deadline", json={"new_deadline": "2100-01-01"})
        assert resp.status_code == 200
        assert resp.json()["application_deadline"] == "2100-01-01"

    def test_eligibility_guaranteed(self, client):
        prog = _create_and_publish_programme(client, aps=20)
        resp = client.get(f"/api/programmes/{prog['programme_id']}/eligibility?learner_aps=24")
        assert resp.status_code == 200
        assert resp.json()["eligibility"] == "Guaranteed"

    def test_eligibility_not_eligible(self, client):
        prog = _create_and_publish_programme(client, aps=30)
        resp = client.get(f"/api/programmes/{prog['programme_id']}/eligibility?learner_aps=20")
        assert resp.status_code == 200
        assert resp.json()["eligibility"] == "NotEligible"


# ─────────────────────────────────────────────────────────────────────────────
# Eligibility assessment hardening tests (REQ-003)
# ─────────────────────────────────────────────────────────────────────────────

class TestEligibilityEndpoint:
    """Verify the eligibility endpoint is explicit about what it has and has not assessed.

    The endpoint supports two modes:
    - APS_ONLY (no learner_id): fast check against the APS margin only.
    - APS_AND_SUBJECTS (learner_id supplied): full check using stored marks.
    The response fields assessment_type and has_subject_requirements make the
    completeness of every result machine-readable so callers cannot accidentally
    treat an APS-only result as a full eligibility decision.
    """

    def test_without_learner_id_is_aps_only(self, client):
        """Omitting learner_id must produce assessment_type=APS_ONLY and
        subject_requirements_checked=False."""
        prog = _create_and_publish_programme(client, aps=20)
        resp = client.get(
            f"/api/programmes/{prog['programme_id']}/eligibility?learner_aps=28"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["assessment_type"] == "APS_ONLY"
        assert body["subject_requirements_checked"] is False
        assert body["eligibility"] == "Guaranteed"  # diff=8 ≥ 4

    def test_aps_only_with_programme_that_has_subject_requirements(self, client):
        """When the programme has required_subjects but no learner_id is provided,
        has_subject_requirements must be True so callers know the result is
        incomplete and cannot be used as a final eligibility decision."""
        prog = _create_and_publish_programme(
            client, aps=20, required_subjects={"Mathematics": 60}
        )
        resp = client.get(
            f"/api/programmes/{prog['programme_id']}/eligibility?learner_aps=28"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["assessment_type"] == "APS_ONLY"
        assert body["has_subject_requirements"] is True
        assert body["subject_requirements_checked"] is False
        # APS says Guaranteed — but subject requirements were NOT checked
        assert body["eligibility"] == "Guaranteed"

    def test_with_learner_id_uses_stored_marks_and_subject_requirements(self, client):
        """With learner_id, stored marks are fetched and subject requirements checked.
        assessment_type must be APS_AND_SUBJECTS."""
        learner = _create_learner(client)
        lid = learner["learner_id"]
        client.post(f"/api/learners/{lid}/marks", json={
            "subject_name": "Mathematics", "score": 65,
            "exam_type": "NSC", "academic_year": 2025,
        })
        prog = _create_and_publish_programme(
            client, aps=20, required_subjects={"Mathematics": 60}
        )
        resp = client.get(
            f"/api/programmes/{prog['programme_id']}/eligibility"
            f"?learner_aps=28&learner_id={lid}"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["assessment_type"] == "APS_AND_SUBJECTS"
        assert body["subject_requirements_checked"] is True
        assert body["has_subject_requirements"] is True
        assert body["eligibility"] == "Guaranteed"  # APS diff=8, Maths 65 ≥ 60

    def test_with_learner_id_subject_not_met_returns_not_eligible(self, client):
        """A learner whose stored Maths mark is below the programme minimum must
        receive NotEligible even if their APS would give Guaranteed."""
        learner = _create_learner(client)
        lid = learner["learner_id"]
        client.post(f"/api/learners/{lid}/marks", json={
            "subject_name": "Mathematics", "score": 50,
            "exam_type": "NSC", "academic_year": 2025,
        })
        prog = _create_and_publish_programme(
            client, aps=20, required_subjects={"Mathematics": 60}
        )
        resp = client.get(
            f"/api/programmes/{prog['programme_id']}/eligibility"
            f"?learner_aps=35&learner_id={lid}"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["eligibility"] == "NotEligible"
        assert body["assessment_type"] == "APS_AND_SUBJECTS"
        assert body["subject_requirements_checked"] is True

    def test_with_nonexistent_learner_id_returns_404(self, client):
        """A non-existent learner_id must return 404 rather than silently
        falling back to an APS-only result."""
        prog = _create_and_publish_programme(client, aps=20)
        resp = client.get(
            f"/api/programmes/{prog['programme_id']}/eligibility"
            f"?learner_aps=28&learner_id={str(uuid4())}"
        )
        assert resp.status_code == 404

    def test_programme_without_subject_requirements_has_subject_requirements_false(self, client):
        """Programmes with no required_subjects must return has_subject_requirements=False."""
        prog = _create_and_publish_programme(client, aps=20)
        resp = client.get(
            f"/api/programmes/{prog['programme_id']}/eligibility?learner_aps=28"
        )
        assert resp.status_code == 200
        assert resp.json()["has_subject_requirements"] is False

    # ── Programme update: required_subjects validation ─────────────────────────

    def test_update_programme_invalid_required_subject_mark_returns_400(self, client):
        """An update that sets a required-subject minimum outside 0-100 must
        be rejected with HTTP 400 before it reaches the domain."""
        prog = _create_programme(client)
        resp = client.put(
            f"/api/programmes/{prog['programme_id']}",
            json={"required_subjects": {"Mathematics": 101}},
        )
        assert resp.status_code == 400

    def test_update_programme_negative_required_subject_mark_returns_400(self, client):
        prog = _create_programme(client)
        resp = client.put(
            f"/api/programmes/{prog['programme_id']}",
            json={"required_subjects": {"Mathematics": -1}},
        )
        assert resp.status_code == 400

    def test_update_programme_valid_required_subjects_persisted(self, client):
        """A valid required_subjects update must be persisted and returned
        in the programme response."""
        prog = _create_programme(client)
        resp = client.put(
            f"/api/programmes/{prog['programme_id']}",
            json={"required_subjects": {"Mathematics": 60, "English": 50}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["required_subjects"] == {"Mathematics": 60, "English": 50}

    def test_update_programme_clear_required_subjects(self, client):
        """Setting required_subjects to an empty dict must remove all requirements."""
        prog = _create_programme(client, required_subjects={"Mathematics": 60})
        resp = client.put(
            f"/api/programmes/{prog['programme_id']}",
            json={"required_subjects": {}},
        )
        assert resp.status_code == 200
        assert resp.json()["required_subjects"] == {}


# ─────────────────────────────────────────────────────────────────────────────
# Application endpoints
# ─────────────────────────────────────────────────────────────────────────────

class TestApplicationEndpoints:

    def test_create_application(self, client):
        learner = _create_eligible_learner(client)
        prog = _create_and_publish_programme(client)
        app = _create_application(client, learner["learner_id"], prog["programme_id"])
        assert app["status"] == "Draft"
        assert app["learner_id"] == learner["learner_id"]

    def test_create_application_learner_not_found_404(self, client):
        prog = _create_and_publish_programme(client)
        resp = client.post("/api/applications", json={
            "learner_id": str(uuid4()),
            "programme_id": prog["programme_id"],
            "fee_amount": "200.00",
        })
        assert resp.status_code == 404

    def test_create_application_programme_not_active_409(self, client):
        learner = _create_eligible_learner(client)
        prog = _create_programme(client)
        resp = client.post("/api/applications", json={
            "learner_id": learner["learner_id"],
            "programme_id": prog["programme_id"],
            "fee_amount": "200.00",
        })
        assert resp.status_code == 409

    def test_ineligible_learner_application_422(self, client):
        """A learner with no marks (APS 0) applying to a programme with min APS 28
        is classified as NotEligible and receives a 422 response."""
        learner = _create_learner(client)  # no marks → APS 0 → NotEligible
        prog = _create_and_publish_programme(client, aps=28)
        resp = client.post("/api/applications", json={
            "learner_id": learner["learner_id"],
            "programme_id": prog["programme_id"],
            "fee_amount": "200.00",
        })
        assert resp.status_code == 422
        assert "NotEligible" in resp.json()["detail"]

    def test_duplicate_application_409(self, client):
        learner = _create_eligible_learner(client)
        prog = _create_and_publish_programme(client)
        _create_application(client, learner["learner_id"], prog["programme_id"])
        resp = client.post("/api/applications", json={
            "learner_id": learner["learner_id"],
            "programme_id": prog["programme_id"],
            "fee_amount": "200.00",
        })
        assert resp.status_code == 409

    def test_more_than_five_applications_allowed(self, client):
        """Removing the cap means an eligible learner can hold more than 5 active applications."""
        learner = _create_eligible_learner(client)
        for _ in range(7):
            prog = _create_and_publish_programme(client)
            app = _create_application(client, learner["learner_id"], prog["programme_id"])
            assert app["status"] == "Draft"

    def test_get_application(self, client):
        learner = _create_eligible_learner(client)
        prog = _create_and_publish_programme(client)
        app = _create_application(client, learner["learner_id"], prog["programme_id"])
        resp = client.get(f"/api/applications/{app['application_id']}")
        assert resp.status_code == 200

    def test_get_nonexistent_application_404(self, client):
        resp = client.get(f"/api/applications/{uuid4()}")
        assert resp.status_code == 404

    def test_list_applications(self, client):
        resp = client.get("/api/applications")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_learner_applications(self, client):
        learner = _create_eligible_learner(client)
        prog = _create_and_publish_programme(client)
        _create_application(client, learner["learner_id"], prog["programme_id"])
        resp = client.get(f"/api/applications/learner/{learner['learner_id']}")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_cancel_application(self, client):
        learner = _create_eligible_learner(client)
        prog = _create_and_publish_programme(client)
        app = _create_application(client, learner["learner_id"], prog["programme_id"])
        resp = client.post(
            f"/api/applications/{app['application_id']}/cancel",
            json={"actor_id": ACTOR_ID},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "Cancelled"

    def test_delete_application(self, client):
        learner = _create_eligible_learner(client)
        prog = _create_and_publish_programme(client)
        app = _create_application(client, learner["learner_id"], prog["programme_id"])
        assert client.delete(f"/api/applications/{app['application_id']}").status_code == 204
        assert client.get(f"/api/applications/{app['application_id']}").status_code == 404

    # ── Compulsory-subject enforcement (REQ-004) ──────────────────────────────

    def test_fails_required_subject_mark_returns_422_no_record(self, client):
        """Learner whose best Mathematics mark is below the programme's required
        minimum receives 422 even when APS is Guaranteed (REQ-004 subject gate).
        No application record must be created.

        Setup: five non-Mathematics subjects at 90 → APS 38 (with Maths 40 in top-6
        the sum is 5×7+3=38; diff 38-28=10 ≥ 4 → Guaranteed by APS alone).
        Programme requires Mathematics ≥ 60; best Mathematics mark is 40 → FAIL.
        """
        learner = _create_learner(client)
        for subj in ["English", "Life Sciences", "Physical Sciences", "History", "Geography"]:
            r = client.post(f"/api/learners/{learner['learner_id']}/marks", json={
                "subject_name": subj, "score": 90, "exam_type": "NSC", "academic_year": 2024,
            })
            assert r.status_code == 201
        r = client.post(f"/api/learners/{learner['learner_id']}/marks", json={
            "subject_name": "Mathematics", "score": 40, "exam_type": "NSC", "academic_year": 2024,
        })
        assert r.status_code == 201

        prog = _create_and_publish_programme(client, aps=28, required_subjects={"Mathematics": 60})
        resp = client.post("/api/applications", json={
            "learner_id": learner["learner_id"],
            "programme_id": prog["programme_id"],
            "fee_amount": "200.00",
        })
        assert resp.status_code == 422
        assert "NotEligible" in resp.json()["detail"]
        # No application record should exist for this learner
        apps = client.get(f"/api/applications/learner/{learner['learner_id']}").json()
        assert apps == []

    def test_missing_required_subject_returns_422_no_record(self, client):
        """Learner with no Mathematics marks at all is rejected when the programme
        requires Mathematics, regardless of APS (REQ-004 subject gate).
        No application record must be created.

        Setup: six non-Mathematics subjects at 90 → APS 42 (diff 42-28=14 → Guaranteed).
        Programme requires Mathematics ≥ 60; learner has no Mathematics mark → FAIL.
        """
        learner = _create_learner(client)
        for subj in ["English", "Life Sciences", "Physical Sciences", "History", "Geography", "Arts"]:
            r = client.post(f"/api/learners/{learner['learner_id']}/marks", json={
                "subject_name": subj, "score": 90, "exam_type": "NSC", "academic_year": 2024,
            })
            assert r.status_code == 201

        prog = _create_and_publish_programme(client, aps=28, required_subjects={"Mathematics": 60})
        resp = client.post("/api/applications", json={
            "learner_id": learner["learner_id"],
            "programme_id": prog["programme_id"],
            "fee_amount": "200.00",
        })
        assert resp.status_code == 422
        assert "NotEligible" in resp.json()["detail"]
        # No application record should exist for this learner
        apps = client.get(f"/api/applications/learner/{learner['learner_id']}").json()
        assert apps == []


# ─────────────────────────────────────────────────────────────────────────────
# Application status history endpoint (REQ-007)
# ─────────────────────────────────────────────────────────────────────────────

class TestApplicationHistoryEndpoint:
    """Integration tests for GET /api/applications/{id}/history (REQ-007).

    Tests use a module-scoped client so each learner/programme/application is
    independent by construction (each test creates its own resources).
    """

    def test_history_empty_for_new_application(self, client):
        """A newly created application (Draft, no transitions yet) must return
        an empty history list."""
        learner = _create_eligible_learner(client)
        prog = _create_and_publish_programme(client)
        app = _create_application(client, learner["learner_id"], prog["programme_id"])

        resp = client.get(f"/api/applications/{app['application_id']}/history")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_history_records_cancellation_all_fields(self, client):
        """After cancellation all StatusHistoryEntry fields must appear in the
        response body with correct values.

        Verified fields: previous_status, new_status, changed_by, changed_at
        (parseable ISO 8601 string), note, entry_id (UUID), application_id.
        """
        learner = _create_eligible_learner(client)
        prog = _create_and_publish_programme(client)
        app = _create_application(client, learner["learner_id"], prog["programme_id"])

        cancel_resp = client.post(
            f"/api/applications/{app['application_id']}/cancel",
            json={"actor_id": ACTOR_ID},
        )
        assert cancel_resp.status_code == 200

        resp = client.get(f"/api/applications/{app['application_id']}/history")
        assert resp.status_code == 200
        entries = resp.json()
        assert len(entries) == 1

        entry = entries[0]
        assert entry["previous_status"] == "Draft"
        assert entry["new_status"] == "Cancelled"
        assert entry["changed_by"] == ACTOR_ID
        assert entry["application_id"] == app["application_id"]
        assert entry["note"] == ""
        # entry_id must be a valid UUID string
        from uuid import UUID as _UUID
        _UUID(entry["entry_id"])
        # changed_at must be a parseable ISO 8601 string
        from datetime import datetime
        datetime.fromisoformat(entry["changed_at"])

    def test_history_records_note_from_status_update(self, client):
        """When a status change is made via PUT /status with a non-empty note,
        that note must appear verbatim in the history entry."""
        learner = _create_eligible_learner(client)
        prog = _create_and_publish_programme(client)
        app = _create_application(client, learner["learner_id"], prog["programme_id"])

        update_resp = client.put(
            f"/api/applications/{app['application_id']}/status",
            json={
                "new_status": "FeeOutstanding",
                "actor_id": ACTOR_ID,
                "note": "Fee request sent to learner",
            },
        )
        assert update_resp.status_code == 200

        resp = client.get(f"/api/applications/{app['application_id']}/history")
        assert resp.status_code == 200
        entries = resp.json()
        assert len(entries) == 1
        assert entries[0]["previous_status"] == "Draft"
        assert entries[0]["new_status"] == "FeeOutstanding"
        assert entries[0]["note"] == "Fee request sent to learner"

    def test_history_chronological_order(self, client):
        """Multiple status changes must appear in chronological order (oldest first).

        Sequence: Draft → FeeOutstanding → FeePaid.
        The second entry's changed_at must be >= the first entry's changed_at.
        """
        learner = _create_eligible_learner(client)
        prog = _create_and_publish_programme(client)
        app = _create_application(client, learner["learner_id"], prog["programme_id"])
        aid = app["application_id"]

        r1 = client.put(f"/api/applications/{aid}/status", json={
            "new_status": "FeeOutstanding", "actor_id": ACTOR_ID, "note": "step 1",
        })
        assert r1.status_code == 200

        r2 = client.put(f"/api/applications/{aid}/status", json={
            "new_status": "FeePaid", "actor_id": ACTOR_ID, "note": "step 2",
        })
        assert r2.status_code == 200

        resp = client.get(f"/api/applications/{aid}/history")
        assert resp.status_code == 200
        entries = resp.json()
        assert len(entries) == 2

        assert entries[0]["previous_status"] == "Draft"
        assert entries[0]["new_status"] == "FeeOutstanding"
        assert entries[0]["note"] == "step 1"

        assert entries[1]["previous_status"] == "FeeOutstanding"
        assert entries[1]["new_status"] == "FeePaid"
        assert entries[1]["note"] == "step 2"

        from datetime import datetime
        t0 = datetime.fromisoformat(entries[0]["changed_at"])
        t1 = datetime.fromisoformat(entries[1]["changed_at"])
        assert t0 <= t1

    def test_history_nonexistent_application_returns_404(self, client):
        """Requesting history for an unknown application_id must return HTTP 404."""
        resp = client.get(f"/api/applications/{uuid4()}/history")
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Per-university APS scoring at application creation — API level (REQ-002)
#
# All ScoringRule instances below are SYNTHETIC test rules. They do not
# represent official admission rules of any South African university.
# ─────────────────────────────────────────────────────────────────────────────

class TestPerUniversityApsApplicationCreation:
    """API-level tests: POST /api/applications uses the university-specific
    APS formula when a ScoringRule is registered for the programme's university
    (REQ-002).
    """

    @pytest.fixture(scope="class")
    def client_for_req002(self):
        """TestClient with a synthetic rule that excludes 'Mathematics'.

        Synthetic rule (NOT an official university rule):
          - Excludes 'Mathematics' from APS calculation.
          - Uses standard NSC bands, top-6 count, no weightings.

        Learner with Mathematics=90 (7pts), English=70 (6pts), LO=50 (4pts):
          NSC APS  = 7+6+4 = 17
          Rule APS = 6+4   = 10  (Mathematics excluded)
        """
        repo = InMemoryScoringRuleRepository()
        synthetic_uni_id = uuid4()
        rule = ScoringRule(
            university_id=synthetic_uni_id,
            band_thresholds=NSC_DEFAULT_SCORING_RULE.band_thresholds,
            subject_count=6,
            excluded_subjects=["Mathematics"],
            subject_weightings={},
        )
        repo.save(rule)
        return {
            "client": TestClient(create_app(scoring_rule_repo=repo)),
            "university_id": str(synthetic_uni_id),
        }

    def test_university_rule_blocks_application_when_nsc_aps_passes(
        self, client_for_req002
    ):
        """When the programme's university has a registered rule, the
        university-specific APS gates the application, not the NSC default.

        Setup: learner with Mathematics=90, English=70, Life Orientation=50
          NSC APS = 7+6+4 = 17 → programme min 12 → diff 5 → Guaranteed (would allow)
          Rule APS = 6+4 = 10 (Mathematics excluded) → diff -2 → NotEligible

        Expected: 422 Unprocessable Entity. No application record created.
        """
        client = client_for_req002["client"]
        uni_id = client_for_req002["university_id"]

        resp = client.post("/api/learners", json={
            "full_name": "Lerato Dube",
            "school_id_number": "REQ002-API-001",
            "grade": 12,
            "counselor_id": str(uuid4()),
            "school_id": str(uuid4()),
        })
        assert resp.status_code == 201
        lid = resp.json()["learner_id"]

        for subj, score in [("Mathematics", 90), ("English", 70), ("Life Orientation", 50)]:
            r = client.post(f"/api/learners/{lid}/marks", json={
                "subject_name": subj, "score": score, "exam_type": "NSC", "academic_year": 2025,
            })
            assert r.status_code == 201

        # Programme belongs to the university with the registered rule;
        # min_aps=12 → NSC APS (17) passes but university APS (10) fails
        resp = client.post("/api/programmes", json={
            "university_id": uni_id,
            "name": "BSc Engineering",
            "faculty": "Engineering",
            "minimum_aps": 12,
            "application_deadline": "2099-12-31",
            "application_fee": "300.00",
            "required_documents": ["ID"],
            "published_by": str(uuid4()),
        })
        assert resp.status_code == 201
        pid = resp.json()["programme_id"]
        assert client.post(f"/api/programmes/{pid}/publish").status_code == 200

        resp = client.post("/api/applications", json={
            "learner_id": lid,
            "programme_id": pid,
            "fee_amount": "300.00",
        })
        assert resp.status_code == 422
        assert "NotEligible" in resp.json()["detail"]

        # Confirm no application record was persisted
        apps = client.get(f"/api/applications/learner/{lid}").json()
        assert apps == []
