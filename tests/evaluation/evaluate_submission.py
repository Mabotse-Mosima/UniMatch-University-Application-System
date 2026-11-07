from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import statistics
import time
from pathlib import Path
import sys
from typing import Any
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from tests.api.test_api import _build_test_context
from tests.api.test_authorization import (
    _create_review_application,
    _make_two_school_app,
    _upload_rag_doc,
)
from unimatch.rag import EMBEDDING_DIMENSIONS, ExtractiveGroundedAnswerProvider


CASE_FILE = Path(__file__).with_name("submission_cases.json")
RESULT_FILE = ROOT / "var" / "evaluation-results.json"


class EvaluationVectorStore:
    """Deterministic, in-memory vector-store stand-in for an isolated API evaluation."""

    def __init__(self) -> None:
        self.rows: dict[str, tuple[Any, list[float]]] = {}
        self.query_calls = 0

    def upsert(self, chunks: list[Any], embeddings: list[list[float]]) -> None:
        self.rows.update(
            {
                chunk.chunk_id: (chunk, embedding)
                for chunk, embedding in zip(chunks, embeddings)
            }
        )

    def reconcile(
        self, allowed_universities: set[str], authoritative_chunk_ids: set[str]
    ) -> int:
        stale = [
            chunk_id
            for chunk_id, (chunk, _embedding) in self.rows.items()
            if chunk.university in allowed_universities
            and chunk_id not in authoritative_chunk_ids
        ]
        for chunk_id in stale:
            del self.rows[chunk_id]
        return len(stale)

    def delete_source(self, source_id: str) -> None:
        self.rows = {
            chunk_id: value
            for chunk_id, value in self.rows.items()
            if value[0].source_id != source_id
        }

    def query(
        self,
        embedding: list[float],
        limit: int,
        allowed_universities: set[str] | None = None,
    ) -> list[tuple[Any, float]]:
        self.query_calls += 1
        allowed = allowed_universities or set()
        scored = []
        for chunk, stored in self.rows.values():
            if chunk.university not in allowed:
                continue
            score = sum(left * right for left, right in zip(embedding, stored))
            if score >= 0.30:
                scored.append((chunk, score))
        scored.sort(key=lambda result: (-result[1], result[0].chunk_id))
        return scored[:limit]


def _hash_embeddings(texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for text in texts:
        vector = [0.0] * EMBEDDING_DIMENSIONS
        for token in re.findall(r"[a-z0-9]+", text.casefold()):
            index = int.from_bytes(hashlib.sha256(token.encode()).digest()[:4], "big")
            vector[index % EMBEDDING_DIMENSIONS] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        vectors.append([value / norm for value in vector])
    return vectors


def _percentiles(samples_ms: list[float]) -> dict[str, float]:
    ordered = sorted(samples_ms)
    return {
        "request_count": len(ordered),
        "median_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)], 3),
        "min_ms": round(ordered[0], 3),
        "max_ms": round(ordered[-1], 3),
    }


def _load_cases() -> dict[str, Any]:
    return json.loads(CASE_FILE.read_text(encoding="utf-8"))


def run_eligibility_evaluation() -> dict[str, Any]:
    cases = _load_cases()["eligibility_cases"]
    context = _build_test_context()
    predictions: list[dict[str, Any]] = []
    learner_ids: list[str] = []
    request_times: list[float] = []
    programme_ids: dict[str, str] = {}

    for case in cases:
        learner_response = context.school_client.post(
            "/api/learners",
            json={
                "full_name": f"Evaluation fixture {case['id']}",
                "school_id_number": f"EVAL-{case['id']}",
                "grade": 12,
                "school_id": str(context.school_id),
            },
            headers={"X-CSRF-Token": context.school_csrf},
        )
        if learner_response.status_code != 201:
            raise AssertionError(
                f"Could not create synthetic learner {case['id']}: "
                f"{learner_response.status_code} {learner_response.text}"
            )
        learner_id = learner_response.json()["learner_id"]
        learner_ids.append(learner_id)

        for mark in case["marks"]:
            response = context.school_client.post(
                f"/api/learners/{learner_id}/marks",
                json={
                    "subject_name": mark["subject"],
                    "score": mark["score"],
                    "exam_type": "NSC",
                    "academic_year": 2025,
                },
                headers={"X-CSRF-Token": context.school_csrf},
            )
            if response.status_code != 201:
                raise AssertionError(
                    f"Could not record fixture mark for {case['id']}: "
                    f"{response.status_code} {response.text}"
                )

        for programme in case["programmes"]:
            programme_response = context.uni_client.post(
                "/api/programmes",
                json={
                    "university_id": str(context.university_id),
                    "name": f"Evaluation {case['id']} {programme['key']}",
                    "faculty": "Synthetic evaluation fixture",
                    "minimum_aps": programme["minimum_aps"],
                    "application_deadline": "2099-12-31",
                    "application_fee": "0.00",
                    "required_documents": [],
                    "published_by": str(uuid4()),
                    "required_subjects": programme["required_subjects"],
                },
                headers={"X-CSRF-Token": context.uni_csrf},
            )
            if programme_response.status_code != 201:
                raise AssertionError(
                    f"Could not create fixture programme {case['id']}: "
                    f"{programme_response.status_code} {programme_response.text}"
                )
            programme_id = programme_response.json()["programme_id"]
            published = context.uni_client.post(
                f"/api/programmes/{programme_id}/publish",
                headers={"X-CSRF-Token": context.uni_csrf},
            )
            if published.status_code != 200:
                raise AssertionError(
                    f"Could not publish fixture programme {case['id']}: "
                    f"{published.status_code} {published.text}"
                )
            programme_ids[programme["key"]] = programme_id

        start = time.perf_counter()
        recommendations_response = context.school_client.get(
            f"/api/learners/{learner_id}/recommendations"
        )
        request_times.append((time.perf_counter() - start) * 1000)
        if recommendations_response.status_code != 200:
            raise AssertionError(
                f"Recommendations failed for {case['id']}: "
                f"{recommendations_response.status_code} "
                f"{recommendations_response.text}"
            )
        recommendations = recommendations_response.json()

        for programme in case["programmes"]:
            actual = next(
                (
                    item
                    for item in recommendations["recommendations"]
                    if item["programme_id"] == programme_ids[programme["key"]]
                ),
                None,
            )
            if actual is None:
                raise AssertionError(
                    f"Recommendation omitted fixture programme {programme['key']}"
                )
            correct = (
                recommendations["learner_aps"] == programme["expected_aps"]
                and actual["eligibility"] == programme["expected_eligibility"]
                and actual["subject_requirements_met"]
                is programme["expected_subjects_met"]
            )
            predictions.append(
                {
                    "case_id": case["id"],
                    "programme_key": programme["key"],
                    "profile": case["profile"],
                    "marks": case["marks"],
                    "minimum_aps": programme["minimum_aps"],
                    "required_subjects": programme["required_subjects"],
                    "expected": {
                        "aps": programme["expected_aps"],
                        "eligibility": programme["expected_eligibility"],
                        "subject_requirements_met": programme[
                            "expected_subjects_met"
                        ],
                    },
                    "actual": {
                        "aps": recommendations["learner_aps"],
                        "eligibility": actual["eligibility"],
                        "subject_requirements_met": actual[
                            "subject_requirements_met"
                        ],
                        "explanation": actual["explanation"],
                    },
                    "passed": correct,
                    "discrepancy": None if correct else "Expected and actual result differ.",
                }
            )

    # Measure catalogue listing and recommendations on the same isolated synthetic dataset.
    catalogue_times: list[float] = []
    for _ in range(10):
        start = time.perf_counter()
        response = context.school_client.get("/api/programmes?published_only=true")
        catalogue_times.append((time.perf_counter() - start) * 1000)
        if response.status_code != 200:
            raise AssertionError(f"Catalogue listing failed: {response.status_code}")

    repeat_recommendation_times: list[float] = []
    for _ in range(10):
        start = time.perf_counter()
        response = context.school_client.get(
            f"/api/learners/{learner_ids[0]}/recommendations"
        )
        repeat_recommendation_times.append((time.perf_counter() - start) * 1000)
        if response.status_code != 200:
            raise AssertionError(
                f"Recommendation timing request failed: {response.status_code}"
            )

    labels = ("Guaranteed", "Likely", "Borderline", "NotEligible")
    confusion = {expected: {actual: 0 for actual in labels} for expected in labels}
    for item in predictions:
        confusion[item["expected"]["eligibility"]][item["actual"]["eligibility"]] += 1
    category_results = {}
    for label in labels:
        selected = [
            item for item in predictions
            if item["expected"]["eligibility"] == label
        ]
        category_results[label] = {
            "total": len(selected),
            "correct": sum(item["passed"] for item in selected),
        }
    correct_count = sum(item["passed"] for item in predictions)
    return {
        "notice": _load_cases()["eligibility_notice"],
        "expected_basis": (
            "Expected APS totals were independently calculated from the checked-in "
            "default mark-to-point bands, top-six rule, and configured programme "
            "thresholds. Labels use the existing service margins: +4 Guaranteed, "
            "+1..+3 Likely, 0 Borderline, below minimum NotEligible; unmet/missing "
            "required subjects override APS to NotEligible."
        ),
        "learner_profiles": len(cases),
        "programme_predictions": len(predictions),
        "correct_predictions": correct_count,
        "incorrect_predictions": len(predictions) - correct_count,
        "accuracy": correct_count / len(predictions) if predictions else 0.0,
        "confusion_matrix_expected_rows_actual_columns": confusion,
        "per_category": category_results,
        "cases": predictions,
        "performance": {
            "recommendations_over_eight_profiles": _percentiles(request_times),
            "recommendations_repeated_on_one_profile": _percentiles(
                repeat_recommendation_times
            ),
            "published_programme_catalogue_listing": _percentiles(catalogue_times),
            "synthetic_dataset": {
                "learner_profiles": len(cases),
                "programme_records": len(programme_ids),
                "marks": sum(len(case["marks"]) for case in cases),
                "database": "in-memory repositories; no PostgreSQL connection",
            },
        },
    }


def _publish_fixture_programme(state: dict[str, Any], university_key: str) -> str:
    university_id = state[university_key]
    client_key = "client_x" if university_key == "uni_x" else "client_y"
    csrf_key = "csrf_x" if university_key == "uni_x" else "csrf_y"
    client = state[client_key]
    response = client.post(
        "/api/programmes",
        json={
            "university_id": str(university_id),
            "name": f"Synthetic Computing {university_key}",
            "faculty": "Synthetic evaluation fixture",
            "minimum_aps": 20,
            "application_deadline": "2099-12-31",
            "application_fee": "0.00",
            "required_documents": [],
            "published_by": str(uuid4()),
        },
        headers={"X-CSRF-Token": state[csrf_key]},
    )
    if response.status_code != 201:
        raise AssertionError(f"Could not create RAG scope fixture: {response.text}")
    programme_id = response.json()["programme_id"]
    publish = client.post(
        f"/api/programmes/{programme_id}/publish",
        headers={"X-CSRF-Token": state[csrf_key]},
    )
    if publish.status_code != 200:
        raise AssertionError(f"Could not publish RAG scope fixture: {publish.text}")
    return programme_id


def run_rag_evaluation() -> dict[str, Any]:
    import unimatch.api as api_module

    cases = _load_cases()["rag"]
    store = EvaluationVectorStore()
    provider = ExtractiveGroundedAnswerProvider()
    state = _make_two_school_app(vector_store=store, answer_provider=provider)
    request_times: list[float] = []
    results: list[dict[str, Any]] = []

    with patch.object(
        api_module, "embed_texts", side_effect=_hash_embeddings
    ):
        for document in cases["documents"]:
            university_key = document["university_key"]
            client_key = "client_x" if university_key == "uni_x" else "client_y"
            csrf_key = "csrf_x" if university_key == "uni_x" else "csrf_y"
            uploaded = _upload_rag_doc(
                state[client_key],
                state[csrf_key],
                document["text"],
                filename=f"{university_key}-synthetic-fixture.docx",
            )
            if uploaded.status_code != 201:
                raise AssertionError(
                    f"Could not upload synthetic RAG fixture: {uploaded.text}"
                )
            document["document_id"] = uploaded.json()["document_id"]
            document["university_id"] = str(state[university_key])

        _publish_fixture_programme(state, "uni_x")
        _publish_fixture_programme(state, "uni_y")

        for case in cases["questions"]:
            university_id = str(state[case["university_key"]])
            start = time.perf_counter()
            response = state["client_a"].post(
                "/api/v1/guidance/assistant/ask",
                json={
                    "question": case["question"],
                    "university_id": university_id,
                },
                headers={"X-CSRF-Token": state["csrf_a"]},
            )
            request_times.append((time.perf_counter() - start) * 1000)
            if response.status_code != 200:
                raise AssertionError(
                    f"RAG evaluation request {case['id']} failed: "
                    f"{response.status_code} {response.text}"
                )
            body = response.json()
            citations = body["citations"]
            expected_fragment = case["expected_fragment"]
            source_match = (
                any(
                    expected_fragment.casefold() in citation["snippet"].casefold()
                    for citation in citations
                )
                if expected_fragment
                else not citations
            )
            citations_valid = all(
                citation["university"] == university_id
                and citation["chunk_id"]
                and citation["snippet"]
                for citation in citations
            )
            grounded = (
                expected_fragment.casefold() in body["answer"].casefold()
                if expected_fragment
                else body["abstained"]
                and "cannot answer" in body["answer"].casefold()
                or body["abstained"]
                and "could not find" in body["answer"].casefold()
            )
            source_text = " ".join(
                citation["snippet"] for citation in citations
            ).casefold()
            numeric_claims_supported = all(
                number.casefold() in source_text
                for number in re.findall(r"\b\d+(?:[.,]\d+)?\b", body["answer"])
            )
            forbidden_fragment = case.get("forbidden_fragment")
            other_university_excluded = (
                forbidden_fragment.casefold() not in body["answer"].casefold()
                if forbidden_fragment
                else True
            )
            passed = (
                body["abstained"] is case["expected_abstained"]
                and source_match
                and citations_valid
                and grounded
                and numeric_claims_supported
                and other_university_excluded
            )
            results.append(
                {
                    "case_id": case["id"],
                    "question": case["question"],
                    "expected_supporting_information": expected_fragment
                    or "No supporting passage; assistant should abstain.",
                    "retrieved_sources": [
                        {
                            "university": citation["university"],
                            "title": citation["title"],
                            "chunk_id": citation["chunk_id"],
                            "snippet": citation["snippet"],
                        }
                        for citation in citations
                    ],
                    "actual_response": body["answer"],
                    "grounded": grounded,
                    "citations_valid": citations_valid and source_match,
                    "numeric_claims_supported": numeric_claims_supported,
                    "other_university_excluded": other_university_excluded,
                    "abstained": body["abstained"],
                    "passed": passed,
                    "reason": (
                        "Expected passage retrieved, answer stayed within it, and citations match authorized source."
                        if passed and expected_fragment
                        else "Unsupported question abstained without citations."
                        if passed
                        else "The answer, retrieval, abstention, or source scope did not meet the fixed expectation."
                    ),
                }
            )

        empty_store = EvaluationVectorStore()
        empty_state = _make_two_school_app(
            vector_store=empty_store,
            answer_provider=provider,
        )
        start = time.perf_counter()
        empty_response = empty_state["client_a"].post(
            "/api/v1/guidance/assistant/ask",
            json={"question": cases["empty_scope_question"]},
            headers={"X-CSRF-Token": empty_state["csrf_a"]},
        )
        empty_elapsed = (time.perf_counter() - start) * 1000
        empty_body = empty_response.json()
        empty_passed = (
            empty_response.status_code == 200
            and empty_body["abstained"]
            and not empty_body["citations"]
            and empty_store.query_calls == 0
        )
        results.append(
            {
                "case_id": "empty_university_scope",
                "question": cases["empty_scope_question"],
                "expected_supporting_information": "No authorized university scope; no vector query or citations.",
                "retrieved_sources": empty_body.get("citations", []),
                "actual_response": empty_body.get("answer", ""),
                "grounded": bool(empty_body.get("abstained")),
                "citations_valid": not empty_body.get("citations"),
                "numeric_claims_supported": not re.findall(
                    r"\b\d+(?:[.,]\d+)?\b", empty_body.get("answer", "")
                ),
                "other_university_excluded": True,
                "abstained": empty_body.get("abstained"),
                "vector_query_calls": empty_store.query_calls,
                "passed": empty_passed,
                "reason": "Empty scope returned an abstention without querying the vector store."
                if empty_passed
                else "Empty-scope behavior was not fail-closed.",
            }
        )

        # Repeated assistant responses measure the full in-memory API retrieval/answer path.
        repeat_times: list[float] = []
        repeat_case = cases["questions"][0]
        for _ in range(10):
            start = time.perf_counter()
            response = state["client_a"].post(
                "/api/v1/guidance/assistant/ask",
                json={
                    "question": repeat_case["question"],
                    "university_id": str(state[repeat_case["university_key"]]),
                },
                headers={"X-CSRF-Token": state["csrf_a"]},
            )
            repeat_times.append((time.perf_counter() - start) * 1000)
            if response.status_code != 200:
                raise AssertionError("Repeated RAG performance request failed.")

    passed_count = sum(item["passed"] for item in results)
    return {
        "notice": cases["notice"],
        "question_count": len(results),
        "passed": passed_count,
        "failed": len(results) - passed_count,
        "accuracy_claim": None,
        "cases": results,
        "performance": {
            "fixed_question_requests": _percentiles(request_times),
            "repeated_retrieval_and_response_requests": _percentiles(repeat_times),
            "synthetic_corpus": {
                "document_count": len(cases["documents"]),
                "university_count": 2,
                "vector_backend": "deterministic in-memory vector test double; no Chroma collection accessed",
                "embedding": "deterministic hashed-token test embedding; not the production model",
            },
            "empty_scope_elapsed_ms": round(empty_elapsed, 3),
        },
    }


def run_end_to_end_workflow() -> dict[str, Any]:
    context = _build_test_context()
    learner = context.school_client.post(
        "/api/learners",
        json={
            "full_name": "Synthetic journey learner",
            "school_id_number": "EVAL-WORKFLOW-001",
            "grade": 12,
            "school_id": str(context.school_id),
        },
        headers={"X-CSRF-Token": context.school_csrf},
    )
    if learner.status_code != 201:
        raise AssertionError(f"Could not create workflow fixture: {learner.text}")
    learner_id = learner.json()["learner_id"]
    for subject, score in (
        ("Mathematics", 80),
        ("English", 80),
        ("Physical Sciences", 80),
        ("Life Sciences", 80),
        ("History", 80),
        ("Geography", 80),
    ):
        response = context.school_client.post(
            f"/api/learners/{learner_id}/marks",
            json={
                "subject_name": subject,
                "score": score,
                "exam_type": "NSC",
                "academic_year": 2025,
            },
            headers={"X-CSRF-Token": context.school_csrf},
        )
        if response.status_code != 201:
            raise AssertionError(f"Could not record workflow mark: {response.text}")

    programme = context.uni_client.post(
        "/api/programmes",
        json={
            "university_id": str(context.university_id),
            "name": "Synthetic workflow programme",
            "faculty": "Synthetic evaluation fixture",
            "minimum_aps": 28,
            "application_deadline": "2099-12-31",
            "application_fee": "100.00",
            "required_documents": [],
            "published_by": str(uuid4()),
            "required_subjects": {"Mathematics": 70},
        },
        headers={"X-CSRF-Token": context.uni_csrf},
    )
    if programme.status_code != 201:
        raise AssertionError(f"Could not create workflow programme: {programme.text}")
    programme_id = programme.json()["programme_id"]
    published = context.uni_client.post(
        f"/api/programmes/{programme_id}/publish",
        headers={"X-CSRF-Token": context.uni_csrf},
    )
    if published.status_code != 200:
        raise AssertionError(f"Could not publish workflow programme: {published.text}")

    recommendations = context.school_client.get(
        f"/api/learners/{learner_id}/recommendations"
    )
    rec = next(
        item
        for item in recommendations.json()["recommendations"]
        if item["programme_id"] == programme_id
    )
    created = context.school_client.post(
        "/api/applications",
        json={
            "learner_id": learner_id,
            "programme_id": programme_id,
            "fee_amount": "100.00",
        },
        headers={"X-CSRF-Token": context.school_csrf},
    )
    if created.status_code != 201:
        raise AssertionError(f"Could not create eligible application: {created.text}")
    application_id = created.json()["application_id"]
    submission = context.school_client.post(
        f"/api/applications/{application_id}/submit",
        headers={"X-CSRF-Token": context.school_csrf},
    )
    return {
        "synthetic_test_data_only": True,
        "steps": [
            {"step": "authenticate school and university accounts", "status": "passed"},
            {"step": "register learner", "status": "passed", "learner_id": learner_id},
            {"step": "capture six academic marks", "status": "passed", "mark_count": 6},
            {
                "step": "publish programme and retrieve recommendation",
                "status": "passed"
                if recommendations.status_code == 200
                and rec["eligibility"] == "Guaranteed"
                else "failed",
                "aps": rec["learner_aps"],
                "eligibility": rec["eligibility"],
                "subject_requirements_met": rec["subject_requirements_met"],
            },
            {
                "step": "create application",
                "status": "passed" if created.status_code == 201 else "failed",
                "application_status": created.json()["status"],
            },
            {
                "step": "submit application",
                "status": "blocked_as_designed"
                if submission.status_code == 409
                else "unexpected",
                "http_status": submission.status_code,
                "detail": submission.json().get("detail"),
            },
            {
                "step": "university-side application review after normal submission",
                "status": "blocked_by_submission_prerequisites",
                "limitation": (
                    "This end-to-end path cannot produce a submitted application because "
                    "payment and document integrations are not available. The review API "
                    "is evaluated separately against a synthetic pre-seeded submitted record."
                ),
            },
        ],
        "external_payment_gateway": "Not configured or exercised; submission requires a recorded payment reference and linked documents.",
    }


def run_university_review_evaluation() -> dict[str, Any]:
    state = _make_two_school_app()
    created, application = _create_review_application(state)
    application_id = created["application_id"]

    own_listing = state["client_x"].get("/api/university/applications")
    if own_listing.status_code != 200:
        raise AssertionError(
            f"University review list failed: {own_listing.status_code}"
        )
    own_records = own_listing.json()
    appears_in_own_scope = any(
        item["application_id"] == application_id for item in own_records
    )

    cross_university = state["client_y"].get(
        f"/api/university/applications/{application_id}"
    )
    if cross_university.status_code != 404:
        raise AssertionError(
            "An application was visible outside its owning university."
        )

    school_decision = state["client_a"].put(
        f"/api/applications/{application_id}/status",
        json={"new_status": "Accepted"},
        headers={"X-CSRF-Token": state["csrf_a"]},
    )
    if school_decision.status_code != 403:
        raise AssertionError(
            "SchoolAdmin was allowed to make an admissions decision."
        )

    # Waitlisted is not a valid transition directly from Submitted.
    invalid_transition = state["client_x"].put(
        f"/api/university/applications/{application_id}/review",
        json={"new_status": "Waitlisted", "note": "Synthetic evaluation"},
        headers={"X-CSRF-Token": state["csrf_x"]},
    )
    if invalid_transition.status_code != 422:
        raise AssertionError(
            "University review accepted an invalid transition (Submitted → Waitlisted)."
        )

    # Direct acceptance from Submitted is intentionally supported by the state machine.
    decision = state["client_x"].put(
        f"/api/university/applications/{application_id}/review",
        json={"new_status": "Accepted", "note": "Synthetic test decision"},
        headers={"X-CSRF-Token": state["csrf_x"]},
    )
    if decision.status_code != 200:
        raise AssertionError(f"University review decision failed: {decision.status_code}")

    response = decision.json()
    reviewer_id = state["client_x"].get("/api/auth/me").json()["account_id"]
    history = response["status_history"]
    decision_history = history[-1]
    return {
        "synthetic_seeded_submitted_application": True,
        "appears_in_own_university_list": appears_in_own_scope,
        "cross_university_access_status": cross_university.status_code,
        "school_administrator_decision_status": school_decision.status_code,
        "invalid_transition_status": invalid_transition.status_code,
        "review_transitions": [entry["new_status"] for entry in history[-2:]],
        "final_status": response["status"],
        "reviewer_identity_recorded": decision_history["changed_by"] == reviewer_id,
        "review_timestamp_recorded": bool(decision_history["changed_at"]),
        "review_note_recorded": (
            decision_history["note"] == "Synthetic test decision"
        ),
        "limitation": (
            "This isolated review fixture is pre-seeded as Submitted to test review "
            "authorization and transitions; it does not demonstrate payment, document "
            "verification, or end-to-end submission."
        ),
    }


def main() -> None:
    logging.getLogger("unimatch.api").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    report = {
        "schema_version": 1,
        "evaluation_source": str(CASE_FILE.relative_to(ROOT)),
        "eligibility": run_eligibility_evaluation(),
        "rag": run_rag_evaluation(),
        "end_to_end_workflow": run_end_to_end_workflow(),
        "university_review": run_university_review_evaluation(),
        "limitations": [
            "All evaluation marks, programmes, and RAG passages are synthetic and are not official university policy.",
            "RAG evaluation used deterministic embeddings and an in-memory vector-store test double, not production Chroma or an external generation provider.",
            "Performance figures are local, single-process TestClient observations on small in-memory datasets; they are not production benchmarks.",
            "Application submission is blocked until required payment and documents are recorded; no payment gateway is integrated.",
            "University review was separately evaluated against a synthetic pre-seeded submitted application because the end-to-end workflow cannot submit without payment and document integrations.",
            "Application document storage and verification are not implemented; linked-document checks do not constitute verification.",
            "PostgreSQL integration tests were not run as part of this evaluation; no database connection was made.",
            "Browser-driven end-to-end and visual accessibility checks were not run.",
        ],
    }
    RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESULT_FILE.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "results_file": str(RESULT_FILE),
                "eligibility": {
                    "profiles": report["eligibility"]["learner_profiles"],
                    "predictions": report["eligibility"]["programme_predictions"],
                    "correct": report["eligibility"]["correct_predictions"],
                    "accuracy": report["eligibility"]["accuracy"],
                },
                "rag": {
                    "questions": report["rag"]["question_count"],
                    "passed": report["rag"]["passed"],
                    "failed": report["rag"]["failed"],
                },
                "university_review": {
                    "final_status": report["university_review"]["final_status"],
                    "own_scope": report["university_review"]["appears_in_own_university_list"],
                    "cross_university_status": report["university_review"]["cross_university_access_status"],
                    "school_decision_status": report["university_review"]["school_administrator_decision_status"],
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
