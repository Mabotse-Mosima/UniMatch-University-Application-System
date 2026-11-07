from __future__ import annotations

from tests.evaluation.evaluate_submission import (
    run_eligibility_evaluation,
    run_end_to_end_workflow,
    run_rag_evaluation,
    run_university_review_evaluation,
)


def test_fixed_eligibility_evaluation_matches_independent_expected_results():
    result = run_eligibility_evaluation()

    assert result["learner_profiles"] == 8
    assert result["programme_predictions"] == 9
    assert result["correct_predictions"] == 9
    assert result["incorrect_predictions"] == 0
    assert result["accuracy"] == 1.0
    assert result["per_category"]["Guaranteed"] == {"total": 1, "correct": 1}
    assert result["per_category"]["Likely"] == {"total": 1, "correct": 1}
    assert result["per_category"]["Borderline"] == {"total": 3, "correct": 3}
    assert result["per_category"]["NotEligible"] == {"total": 4, "correct": 4}


def test_fixed_rag_evaluation_checks_grounding_citations_scope_and_abstention():
    result = run_rag_evaluation()

    assert result["question_count"] == 5
    assert result["passed"] == 5
    assert result["failed"] == 0
    assert result["accuracy_claim"] is None
    assert all(
        case["numeric_claims_supported"] and case["other_university_excluded"]
        for case in result["cases"]
    )


def test_school_to_university_workflow_reports_prerequisite_boundary():
    result = run_end_to_end_workflow()

    assert result["steps"][3]["status"] == "passed"
    assert result["steps"][4]["status"] == "passed"
    assert result["steps"][5]["status"] == "blocked_as_designed"
    assert result["steps"][6]["status"] == "blocked_by_submission_prerequisites"


def test_university_review_is_scoped_and_auditable_on_seeded_submission():
    result = run_university_review_evaluation()

    assert result["synthetic_seeded_submitted_application"] is True
    assert result["appears_in_own_university_list"] is True
    assert result["cross_university_access_status"] == 404
    assert result["school_administrator_decision_status"] == 403
    assert result["invalid_transition_status"] == 422
    # Direct Submitted → Accepted is now supported; UnderReview is no longer a required step.
    assert result["review_transitions"][-1] == "Accepted"
    assert result["final_status"] == "Accepted"
    assert result["reviewer_identity_recorded"] is True
    assert result["review_timestamp_recorded"] is True
    assert result["review_note_recorded"] is True
