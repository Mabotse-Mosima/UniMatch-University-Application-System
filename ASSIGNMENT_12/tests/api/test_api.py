"""
tests/api/test_api.py
=====================
Integration tests for the UniMatch REST API (Assignment 12).

Uses FastAPI's built-in TestClient (wraps httpx) to exercise all endpoints
end-to-end through the full stack: API → Service → In-Memory Repository.
"""

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api import create_app


# ─────────────────────────────────────────────────────────────────────────────
# Shared client fixture (fresh app per test session)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """A fresh TestClient backed by fresh in-memory repos."""
    return TestClient(create_app())


# ── Helpers ──────────────────────────────────────────────────────────────────

COUNSELOR_ID = str(uuid4())
SCHOOL_ID = str(uuid4())
UNIVERSITY_ID = str(uuid4())
PUBLISHER_ID = str(uuid4())
ACTOR_ID = str(uuid4())
FAR_FUTURE = "2099-12-31"


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


def _create_programme(client: TestClient, deadline: str = FAR_FUTURE, aps: int = 28) -> dict:
    resp = client.post("/api/programmes", json={
        "university_id": UNIVERSITY_ID,
        "name": "BSc Computer Science",
        "faculty": "Science",
        "minimum_aps": aps,
        "application_deadline": deadline,
        "application_fee": "200.00",
        "required_documents": ["ID", "Matric Certificate"],
        "published_by": PUBLISHER_ID,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def _publish_programme(client: TestClient, pid: str) -> dict:
    resp = client.post(f"/api/programmes/{pid}/publish")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _create_and_publish_programme(client: TestClient, aps: int = 28) -> dict:
    prog = _create_programme(client, aps=aps)
    return _publish_programme(client, prog["programme_id"])


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
            "score": 150,  # rejected by schema (max 100)
            "exam_type": "NSC",
            "academic_year": 2024,
        })
        assert resp.status_code == 422

    def test_get_aps_score(self, client):
        learner = _create_learner(client)
        # Add mark: score 80 → 6 APS points
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
        # All returned must be active
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
# Application endpoints
# ─────────────────────────────────────────────────────────────────────────────

class TestApplicationEndpoints:

    def test_create_application(self, client):
        learner = _create_learner(client)
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
        learner = _create_learner(client)
        prog = _create_programme(client)  # Draft, not Published
        resp = client.post("/api/applications", json={
            "learner_id": learner["learner_id"],
            "programme_id": prog["programme_id"],
            "fee_amount": "200.00",
        })
        assert resp.status_code == 409

    def test_duplicate_application_409(self, client):
        learner = _create_learner(client)
        prog = _create_and_publish_programme(client)
        _create_application(client, learner["learner_id"], prog["programme_id"])
        resp = client.post("/api/applications", json={
            "learner_id": learner["learner_id"],
            "programme_id": prog["programme_id"],
            "fee_amount": "200.00",
        })
        assert resp.status_code == 409

    def test_active_application_cap_422(self, client):
        """Applying to a 6th programme should return 422."""
        learner = _create_learner(client)
        for _ in range(5):
            prog = _create_and_publish_programme(client)
            _create_application(client, learner["learner_id"], prog["programme_id"])
        extra = _create_and_publish_programme(client)
        resp = client.post("/api/applications", json={
            "learner_id": learner["learner_id"],
            "programme_id": extra["programme_id"],
            "fee_amount": "200.00",
        })
        assert resp.status_code == 422

    def test_get_application(self, client):
        learner = _create_learner(client)
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
        learner = _create_learner(client)
        prog = _create_and_publish_programme(client)
        _create_application(client, learner["learner_id"], prog["programme_id"])
        resp = client.get(f"/api/applications/learner/{learner['learner_id']}")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_cancel_application(self, client):
        learner = _create_learner(client)
        prog = _create_and_publish_programme(client)
        app = _create_application(client, learner["learner_id"], prog["programme_id"])
        resp = client.post(f"/api/applications/{app['application_id']}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "Cancelled"

    def test_delete_application(self, client):
        learner = _create_learner(client)
        prog = _create_and_publish_programme(client)
        app = _create_application(client, learner["learner_id"], prog["programme_id"])
        assert client.delete(f"/api/applications/{app['application_id']}").status_code == 204
        assert client.get(f"/api/applications/{app['application_id']}").status_code == 404
