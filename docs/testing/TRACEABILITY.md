# Requirements-to-Tests Traceability Matrix

**Project:** UniMatch — School-Based University Eligibility Recommender for South African Matriculants  
**Phase:** Implementation, Testing and Evaluation  
**Historical matrix snapshot:** Last updated 2026-10-28 (Phase 1-G comparison implementation)
**Test command:** `python -m pytest tests/ -v`  
**Historical test result:** 193 passed, 0 failed, 0 errors (run 2026-10-20 — see Test execution evidence for detail; not current verification)

> **Latest verification:** This matrix preserves earlier requirement mappings and
> historical test results. The latest verified backend, frontend, and synthetic
> evaluation results are recorded in
> [IMPLEMENTATION_TESTING_EVALUATION.md](IMPLEMENTATION_TESTING_EVALUATION.md).

---

## How to read this document

Each row maps one approved requirement to the test(s) that verify it. Where a
requirement is not yet covered by automated tests, the Coverage column notes
the gap. Where a requirement cannot be tested in the current pilot (e.g.
because a planned feature is not yet implemented), it is noted as
**NOT YET IMPLEMENTED**.

Test IDs use the format `<file>::<Class>::<test_function>`.

---

## Internal requirement identifiers (REQ-NNN)

These labels are used in source-code comments and test docstrings. They map to
the approved spec's functional requirements as follows:

| REQ ID | Description | Spec cross-reference |
|---|---|---|
| REQ-002 | Per-university APS scoring rule | SPEC §3.4 FR-12; SRD FR3/FR4 |
| REQ-003 | Eligibility classification with compulsory subject requirements | SPEC §3.4 FR-13, FR-14; SRD FR4 |
| REQ-004 | Application creation eligibility gating (Guaranteed/Likely only) | SPEC §3.2 FR-5; SRD FR5 |
| REQ-005 | Improvement simulation — **provisional ID, not in approved specification** (see note) | Closest basis: SPEC §3.4 FR-13; source: project gap analysis and Phase 1-G task instruction |
| REQ-007 | Application status-change audit trail | SPEC §3.2 FR-8; SRD FR5, FR15 |

REQ-001, REQ-006, and REQ-008 are reserved for future assignment.

> **Note on REQ-005.** REQ-005 was reserved for future assignment in the original version of this table. It has since been provisionally assigned to the improvement-simulation feature, which was identified as a gap in this traceability document and implemented following an approved project task instruction on 2026-10-20. REQ-005 does **not** correspond to a named requirement in the approved SPECIFICATION.md or SYSTEM_REQUIREMENTS_COMPLETE.md. The closest approved basis is SPECIFICATION.md §3.4 FR-13 ("The system shall compare learner marks and APS score to each programme's minimum requirements"), which the simulation extends by applying that comparison to a temporary, caller-supplied mark set rather than the learner's stored marks. REQ-005 should be treated as a provisional project tracking identifier only until formal approval is recorded.

---

## Functional Requirements

### APS Calculation and Eligibility (FR3, FR4 / REQ-002, REQ-003)

| Req ID | Requirement summary | Test ID | Status |
|---|---|---|---|
| FR3 | APS calculation — NSC 7-point scale applied to individual marks | `tests/test_domain_entities.py::test_mark_aps_points` | PASS |
| FR3 | APS calculation — top-6 subjects rule | `tests/services/test_services.py::TestLearnerProfileService::test_aps_score_top_6` | PASS |
| FR3 | APS calculation — fewer than 6 subjects uses all marks | `tests/services/test_services.py::TestLearnerProfileService::test_aps_fewer_than_6_subjects` | PASS |
| FR3 | APS exposed via API | `tests/api/test_api.py::TestLearnerEndpoints::test_get_aps_score` | PASS |
| FR3/REQ-002 | Per-university APS formula applied when ScoringRule registered | `tests/services/test_services.py::TestScoringRule::*` (5 tests) | PASS |
| FR3/REQ-002 | ScoringRule validation (band thresholds, subject counts, weightings) | `tests/services/test_services.py::TestScoringRuleValidation::*` (17 tests) | PASS |
| FR3/REQ-002 | Per-university APS via API endpoint | `tests/api/test_api.py::TestPerUniversityAps::*` (5 tests) | PASS |
| FR3/REQ-002 | Per-university APS applied in application creation | `tests/services/test_services.py::TestApplicationServiceREQ002::*` (7 tests) | PASS |
| FR3/REQ-002 | Per-university APS enforced at POST /api/applications | `tests/api/test_api.py::TestPerUniversityApsApplicationCreation::*` (1 test) | PASS |
| FR4 | Categories: Guaranteed, Likely, Borderline, Not Eligible | `tests/services/test_services.py::TestUniversityProgrammeService::test_eligibility_*` | PASS |
| FR4 | Eligibility via API | `tests/api/test_api.py::TestProgrammeEndpoints::test_eligibility_*` | PASS |
| FR4/REQ-003 | Compulsory-subject gate in eligibility assessment | `tests/services/test_services.py::TestSubjectRequirements::*` (20 tests) | PASS |
| FR4/REQ-003 | Eligibility endpoint with stored learner marks and subject check | `tests/api/test_api.py::TestEligibilityEndpoint::*` (10 tests) | PASS |
| FR4/REQ-003 | Subject failure blocks application even with passing APS | `tests/services/test_services.py::TestApplicationServiceEligibilityEnforcement::test_high_aps_but_fails_compulsory_subject_rejected` | PASS |
| FR4/REQ-003 | University rule + subject check combined | `tests/services/test_services.py::TestApplicationServiceREQ002::test_university_rule_with_*` (2 tests) | PASS |
| FR-13 ext./REQ-005 | Improvement simulation — service layer (13 tests; see §Improvement Simulation below) | `tests/services/test_services.py::TestSimulateEligibility::*` | PASS |
| FR-13 ext./REQ-005 | Improvement simulation — API layer, including current/projected programme comparison | `tests/api/test_api.py::TestSimulateEligibilityEndpoint::*` | PASS — 9 focused tests passed on 2026-10-28 |

### Improvement Simulation (FR-13 extension / REQ-005 provisional)

> **Provenance.** This feature was not part of the original approved specification. It was identified as a gap in the project's traceability review and approved for implementation via a subsequent task instruction (Phase 1-G, 2026-10-20). The closest approved specification basis is SPECIFICATION.md §3.4 FR-13. REQ-005 is a provisional project tracking identifier; see the note in the REQ-NNN table above.

**Implementation summary:**
- Service method: `LearnerProfileService.simulate_eligibility(learner_id, programme_id, overrides)`
  (`src/unimatch/services/__init__.py`)
- Result type: `SimulationResult` dataclass (`src/unimatch/services/__init__.py`)
- API endpoint: `POST /api/learners/{learner_id}/simulate-eligibility`
- Comparison endpoint: `POST /api/learners/{learner_id}/simulate-eligibility/comparison`
  (`src/unimatch/api/__init__.py`)
- Request schema: `SimulateEligibilityRequest` — `programme_id` (UUID) + `overrides` (dict of subject→score, 0–100)
- Response schema: `SimulationResponse` — `simulated_aps`, `eligibility`, `subject_requirements_checked`, `university_rule_applied`, `is_simulation` (always `true`)
- Comparison results return current and projected APS and eligibility per programme, using university-specific scoring when configured.

**Override semantics (documented for traceability):**
Overrides are added as additional mark entries to the learner's stored marks. This is consistent with the existing system policy: `meets_subject_requirements` uses the best (highest) mark per subject; `get_aps_score` and `calc_aps_for_university` treat every mark entry individually in the ranked pool. No stored mark, entity, or repository record is modified.

**Detailed test coverage:**

| Test | What it verifies |
|---|---|
| `TestSimulateEligibility::test_improvement_changes_aps_and_eligibility` | Override raises APS, lifting eligibility from NotEligible to Guaranteed |
| `TestSimulateEligibility::test_override_below_compulsory_subject_threshold` | Override below required subject minimum → NotEligible |
| `TestSimulateEligibility::test_missing_compulsory_subject_supplied_via_override` | Required subject absent from stored marks satisfied via override |
| `TestSimulateEligibility::test_university_rule_applied_when_registered` | University-specific ScoringRule applied; `university_rule_applied=True` |
| `TestSimulateEligibility::test_nsc_fallback_when_no_rule_registered` | NSC formula used when no rule registered; `university_rule_applied=False` |
| `TestSimulateEligibility::test_nonexistent_learner_raises` | `LearnerNotFoundError` raised |
| `TestSimulateEligibility::test_nonexistent_programme_raises` | `ProgrammeNotFoundError` raised |
| `TestSimulateEligibility::test_invalid_override_score_above_100_raises` | `ValueError` raised at service level |
| `TestSimulateEligibility::test_invalid_override_score_below_0_raises` | `ValueError` raised at service level |
| `TestSimulateEligibility::test_stored_marks_unchanged_after_successful_simulation` | `mark_id` and `score` of every stored mark identical before and after |
| `TestSimulateEligibility::test_stored_marks_unchanged_after_validation_failure` | Stored marks unchanged even when `ValueError` is raised |
| `TestSimulateEligibility::test_no_repository_write_occurs` | Learner, programme, and application repo record counts unchanged |
| `TestSimulateEligibility::test_duplicate_subject_override_uses_best_mark_policy` | Lower override and higher stored mark both enter pool; existing best-mark policy governs |
| `TestSimulateEligibilityEndpoint::test_simulate_improves_eligibility_and_returns_simulation_flag` | HTTP 200; correct APS/eligibility; `is_simulation=true` |
| `TestSimulateEligibilityEndpoint::test_simulate_stored_marks_unchanged_after_endpoint_call` | `mark_count` on learner unchanged after API call |
| `TestSimulateEligibilityEndpoint::test_simulate_nonexistent_learner_returns_404` | HTTP 404 |
| `TestSimulateEligibilityEndpoint::test_simulate_nonexistent_programme_returns_404` | HTTP 404 |
| `TestSimulateEligibilityEndpoint::test_simulate_invalid_override_score_returns_422` | Pydantic rejects score 150 with HTTP 422 |
| `TestSimulateEligibilityEndpoint::test_simulate_uses_registered_university_scoring_rule` | API applies the configured university rule and returns explicit simulation flags |
| `TestSimulateEligibilityEndpoint::test_comparison_returns_current_and_projected_results_for_each_programme` | Returns both results for each programme and leaves marks and applications unchanged |
| `TestSimulateEligibilityEndpoint::test_comparison_uses_programme_university_scoring_rule` | Comparison applies configured university scoring |
| `TestSimulateEligibilityEndpoint::test_comparison_rejects_invalid_marks_without_changing_records` | Rejects an out-of-range mark and leaves marks and applications unchanged |

Focused verification on 2026-10-28: `python -m pytest -q tests/api/test_api.py -k "comparison or simulate_"` — 9 passed, 59 deselected. This was not a full backend test-suite run.

---

### Learner Profile Management (FR1, FR2)

| Req ID | Requirement summary | Test ID | Status |
|---|---|---|---|
| FR1 | Create learner profile | `tests/services/test_services.py::TestLearnerProfileService::test_create_and_get_profile` | PASS |
| FR1 | Create learner profile via API | `tests/api/test_api.py::TestLearnerEndpoints::test_create_learner` | PASS |
| FR1 | Retrieve learner profile | `tests/services/test_services.py::TestLearnerProfileService::test_create_and_get_profile` | PASS |
| FR1 | Retrieve learner — not found returns 404 | `tests/api/test_api.py::TestLearnerEndpoints::test_get_nonexistent_learner_404` | PASS |
| FR1 | Update learner profile | `tests/services/test_services.py::TestLearnerProfileService::test_update_profile` | PASS |
| FR1 | Update via API | `tests/api/test_api.py::TestLearnerEndpoints::test_update_learner` | PASS |
| FR1 | Delete learner profile | `tests/services/test_services.py::TestLearnerProfileService::test_delete_profile` | PASS |
| FR1 | Delete via API | `tests/api/test_api.py::TestLearnerEndpoints::test_delete_learner` | PASS |
| FR1 | List all learner profiles | `tests/services/test_services.py::TestLearnerProfileService::test_list_profiles` | PASS |
| FR1 | List via API | `tests/api/test_api.py::TestLearnerEndpoints::test_list_learners` | PASS |
| FR1 | Add valid mark to learner profile | `tests/services/test_services.py::TestLearnerProfileService::test_add_valid_mark` | PASS |
| FR1 | Mark score out of valid range is rejected | `tests/services/test_services.py::TestLearnerProfileService::test_add_invalid_mark_raises` | PASS |
| FR1 | Mark score >100 rejected by API schema | `tests/api/test_api.py::TestLearnerEndpoints::test_add_invalid_mark_422` | PASS |
| FR1 | Deactivate profile cancels active applications | `tests/services/test_services.py::TestLearnerProfileService::test_deactivate_cancels_active_applications` | PASS |
| FR1 | Deactivate profile records system history entry | `tests/services/test_services.py::TestLearnerProfileService::test_deactivate_records_system_cancellation_in_history` | PASS |
| FR1 | Deactivate via API | `tests/api/test_api.py::TestLearnerEndpoints::test_deactivate_learner` | PASS |
| FR2 | Bulk CSV import of marks | — | **NOT YET IMPLEMENTED** |

### Programme Management (FR13)

| Req ID | Requirement summary | Test ID | Status |
|---|---|---|---|
| FR13 | Create university programme | `tests/services/test_services.py::TestUniversityProgrammeService::test_create_and_get_programme` | PASS |
| FR13 | Create via API | `tests/api/test_api.py::TestProgrammeEndpoints::test_create_programme` | PASS |
| FR13 | Publish programme (deadline must be in future) | `tests/services/test_services.py::TestUniversityProgrammeService::test_publish_programme` | PASS |
| FR13 | Publish rejected when deadline has passed | `tests/services/test_services.py::TestUniversityProgrammeService::test_publish_with_past_deadline_raises` | PASS |
| FR13 | Publish rejected when deadline has passed — API | `tests/api/test_api.py::TestProgrammeEndpoints::test_publish_expired_programme_400` | PASS |
| FR13 | Deactivate published programme | `tests/services/test_services.py::TestUniversityProgrammeService::test_deactivate_programme` | PASS |
| FR13 | Deactivate via API | `tests/api/test_api.py::TestProgrammeEndpoints::test_deactivate_programme` | PASS |
| FR13 | Cannot deactivate a Draft programme | `tests/services/test_services.py::TestUniversityProgrammeService::test_deactivate_draft_programme_raises` | PASS |
| FR13 | Cannot delete a Published programme | `tests/services/test_services.py::TestUniversityProgrammeService::test_delete_published_programme_raises` | PASS |
| FR13 | Programme name cannot be set to blank | `tests/services/test_services.py::TestUniversityProgrammeService::test_update_programme_blank_name_raises` | PASS |
| FR13 | Extend application deadline | `tests/api/test_api.py::TestProgrammeEndpoints::test_extend_deadline` | PASS |
| FR13 | List published programmes only | `tests/services/test_services.py::TestUniversityProgrammeService::test_list_published_only` | PASS |
| FR13 | List published only via API | `tests/api/test_api.py::TestProgrammeEndpoints::test_list_published_only` | PASS |
| FR13 | Required-subject requirements stored and validated | `tests/services/test_services.py::TestSubjectRequirements::test_required_subjects_*` | PASS |
| FR13 | Staleness detection when requirements change | — | **NOT YET IMPLEMENTED** |

### Application Lifecycle (FR5 / REQ-004, REQ-007)

| Req ID | Requirement summary | Test ID | Status |
|---|---|---|---|
| FR5/REQ-004 | Create application — success (Guaranteed learner) | `tests/services/test_services.py::TestApplicationService::test_create_application_success` | PASS |
| FR5/REQ-004 | Create application via API | `tests/api/test_api.py::TestApplicationEndpoints::test_create_application` | PASS |
| FR5/REQ-004 | Application rejected if learner not found | `tests/services/test_services.py::TestApplicationService::test_create_application_learner_not_found` | PASS |
| FR5/REQ-004 | Application rejected if programme not found | `tests/services/test_services.py::TestApplicationService::test_create_application_programme_not_found` | PASS |
| FR5/REQ-004 | Application rejected if programme not active (Draft) | `tests/services/test_services.py::TestApplicationService::test_create_application_programme_not_active` | PASS |
| FR5/REQ-004 | Application rejected if programme has expired | `tests/services/test_services.py::TestApplicationService::test_create_application_expired_programme` | PASS |
| FR5/REQ-004 | Duplicate application rejected | `tests/services/test_services.py::TestApplicationService::test_create_application_duplicate_rejected` | PASS |
| FR5/REQ-004 | Duplicate application rejected via API (409) | `tests/api/test_api.py::TestApplicationEndpoints::test_duplicate_application_409` | PASS |
| FR5/REQ-004 | Borderline learner rejected | `tests/services/test_services.py::TestApplicationServiceEligibilityEnforcement::test_borderline_learner_application_rejected` | PASS |
| FR5/REQ-004 | NotEligible learner rejected | `tests/services/test_services.py::TestApplicationServiceEligibilityEnforcement::test_not_eligible_learner_application_rejected` | PASS |
| FR5/REQ-004 | Rejected application not persisted | `tests/services/test_services.py::TestApplicationServiceEligibilityEnforcement::test_rejected_application_not_persisted` | PASS |
| FR5/REQ-004 | Ineligible learner rejected via API (422) | `tests/api/test_api.py::TestApplicationEndpoints::test_ineligible_learner_application_422` | PASS |
| FR5 | Cancel application | `tests/services/test_services.py::TestApplicationService::test_cancel_application` | PASS |
| FR5 | Cancel application via API | `tests/api/test_api.py::TestApplicationEndpoints::test_cancel_application` | NOT RUN — assertion updated |
| FR5 | Cannot cancel an Accepted application | `tests/services/test_services.py::TestApplicationService::test_cancel_accepted_application_raises` | PASS |
| FR5 | Cancelled applications do not block re-application | `tests/services/test_services.py::TestApplicationService::test_cancelled_applications_dont_block_new_applications` | PASS |
| FR5 | Application cannot be submitted past deadline | `tests/test_domain_entities.py::test_application_can_submit_guard` | PASS |
| FR5 | Programme deadline validation on publish | `tests/test_domain_entities.py::test_university_programme_publish_deadline_rule` | PASS |
| FR5 | Generic status update via API | `tests/api/test_api.py::TestApplicationHistoryEndpoint::test_history_records_note_from_status_update` | PASS |
| FR5/REQ-007 | Status history recorded on entity | `tests/services/test_services.py::TestApplicationService::test_cancel_records_status_history_entry` | PASS |
| FR5/REQ-007 | Cancellation note is retained in status history | `tests/services/test_services.py::TestApplicationService::test_cancel_records_status_history_entry`; `tests/api/test_api.py::TestApplicationEndpoints::test_cancel_application` | NOT RUN — updated assertions pending |
| FR5/REQ-007 | Status history exposed via API — empty for new application | `tests/api/test_api.py::TestApplicationHistoryEndpoint::test_history_empty_for_new_application` | PASS |
| FR5/REQ-007 | Status history — cancellation records all fields | `tests/api/test_api.py::TestApplicationHistoryEndpoint::test_history_records_cancellation_all_fields` | PASS |
| FR5/REQ-007 | Status history — note forwarded from update | `tests/api/test_api.py::TestApplicationHistoryEndpoint::test_history_records_note_from_status_update` | PASS |
| FR5/REQ-007 | Status history — chronological order | `tests/api/test_api.py::TestApplicationHistoryEndpoint::test_history_chronological_order` | PASS |
| FR5/REQ-007 | Status history — 404 for nonexistent application | `tests/api/test_api.py::TestApplicationHistoryEndpoint::test_history_nonexistent_application_returns_404` | PASS |

### University Application Review (current implementation)

The current review API exposes `GET /api/university/applications`,
`GET /api/university/applications/{application_id}`, and
`PUT /api/university/applications/{application_id}/review`. Review routes
require `UniversityAdmissions` and scope records to the university owning the
programme. Cross-university access is denied; learners cannot review, and
`SchoolAdmin` users cannot make admissions decisions. Review transitions are
validated, and a document request requires a nonblank note.

| Behavior | Test ID | Status |
|---|---|---|
| University lists and reviews its submitted applications | `tests/api/test_authorization.py::TestUniversityIsolation::test_university_can_review_its_submitted_applications` | PASS |
| Cross-university application access is denied | `tests/api/test_authorization.py::TestUniversityIsolation::test_university_cannot_access_another_universitys_application` | PASS |
| SchoolAdmin cannot make admissions decisions | `tests/api/test_authorization.py::TestUniversityIsolation::test_school_admin_cannot_make_admission_decisions` | PASS |
| Learner cannot review or approve applications | `tests/api/test_authorization.py::TestUniversityIsolation::test_learner_cannot_access_or_approve_applications` | PASS |
| Invalid transitions and blank document requests are rejected | `tests/api/test_authorization.py::TestUniversityIsolation::test_university_review_rejects_invalid_transitions_and_blank_document_request` | PASS |

The React/TypeScript frontend routes `UniversityAdmissions` users to the
university review screen. Type-check and production build passed in the latest
verification. Browser-based review-flow and visual accessibility checks remain
unperformed.

### User account entity (domain)

| Req ID | Requirement summary | Test ID | Status |
|---|---|---|---|
| FR10 | Account locks after 3 failed login attempts | `tests/test_domain_entities.py::test_user_account_locks_after_three_failures` | PASS |

### Reporting (FR9, FR11)

| Req ID | Requirement summary | Test ID | Status |
|---|---|---|---|
| FR9 | Generate downloadable reports (PDF/CSV) | (ReportingService stub in domain_services.py; no API endpoint) | **NOT YET IMPLEMENTED** |
| FR11 | Department of Education anonymized analytics | — | **NOT YET IMPLEMENTED** |

### Documents and notifications (FR6, FR8, FR12)

| Req ID | Requirement summary | Test ID | Status |
|---|---|---|---|
| FR6 | Upload PDF/DOC/DOCX, validate file signature/type/size, and persist learner-document metadata locally | `tests/api/test_api.py::test_learner_documents_are_stored_reviewed_and_block_paymentless_submission`; `tests/test_document_storage.py::test_local_document_metadata_and_review_survive_repository_restart`; `tests/test_document_storage.py::test_upload_validation_checks_extension_mime_size_and_signature` | PASS — focused tests; PostgreSQL persistence not verified |
| FR6 | Prevent cross-school document download/review; record human review identity, time, and note | `tests/api/test_authorization.py::TestSchoolIsolation::test_other_school_cannot_download_or_review_learner_document`; `tests/api/test_api.py::test_learner_documents_are_stored_reviewed_and_block_paymentless_submission` | PASS — focused tests |
| FR6 | Malware/virus scanning | — | **NOT IMPLEMENTED** — files are explicitly marked `NotScanned`; human review is not malware scanning |
| FR6 | PostgreSQL document metadata migration and persistence | `migrations/versions/0008_learner_document_storage.py` | **NOT VERIFIED** — migration is unapplied; no approved isolated database was available |
| FR8 | Deadline reminder notifications | (Notification entity implemented; no dispatcher) | **PARTIAL** |
| FR12 | Parent/guardian access to application status | — | **NOT YET IMPLEMENTED** |

Local development stores document bytes under `DOCUMENT_STORAGE_DIR` (default
`~/.unimatch/documents`) and metadata in `documents.json` within that directory.
The JSON repository is intended for a single API process. Production/multi-worker
use requires PostgreSQL migration `0008_learner_document_storage` and a shared,
durable private file store; neither has been integration-tested here.

---

## Non-Functional Requirements

| Req ID | Requirement summary | Verification method | Status |
|---|---|---|---|
| NFR1 | WCAG 2.1 AA accessibility | Manual / automated frontend audit | **NOT YET VERIFIED** (frontend exists; browser-based and visual accessibility testing were not performed) |
| NFR4 | Docker deployment | `docker-compose up --build` | Dockerfile and compose provided; not run in CI yet |
| NFR5 | Automated CI/CD pipeline | GitHub Actions `ci.yml` runs on every push | IMPLEMENTED |
| NFR7 | Modular layered architecture | Code structure review | PASS — domain / services / repositories / API layers separated |
| NFR8 | Code coverage for critical modules | `pytest --cov=src/unimatch` | Service + API layers covered; exact % to be measured |
| NFR13 | TLS encryption in transit | Deployment configuration | **NOT YET VERIFIED** (pilot uses HTTP) |
| NFR14 | Role-based access control | API authorization and role-scope tests | Implemented in the current API; targeted authorization tests pass. Production deployment security remains unverified. |
| NFR15 | POPIA compliance — anonymized reporting | — | **NOT YET IMPLEMENTED** |
| NFR17 | Response time ≤ 2 seconds | Performance testing (future) | **NOT YET MEASURED** |
| NFR18 | Recommendations ≤ 3 seconds | Performance testing (future) | **NOT YET MEASURED** |
| NFR19 | 500 concurrent users | Load testing (future) | **NOT YET MEASURED** |

---

## Test execution evidence

### Phase 1-F (2026-10-20)

**Command run:** `python -m pytest tests/ -v`  
**Date:** 2026-10-20  
**Environment:** Python 3.12.4, pytest 9.0.3, Windows 11  
**Result:** 175 passed, 0 failed, 0 errors in 1.86 s  
**Commit:** `90db1e4` fix: enforce university-specific APS during application creation

```
tests/api/test_api.py        — 59 tests (API integration)
tests/services/test_services.py — 112 tests (service unit)
tests/test_domain_entities.py   —   4 tests (domain entities)
```

### Phase 1-G (2026-10-20, same calendar day as the code change)

**Command run:** `python -m pytest --tb=short`  
**Date:** 2026-10-20  
**Environment:** Python 3.12.4, pytest 9.0.3, Windows 11  
**Result:** 193 passed, 0 failed, 0 skipped, 0 errors in 1.94 s

```
tests/api/test_api.py        — 64 tests (API integration)
tests/services/test_services.py — 125 tests (service unit)
tests/test_domain_entities.py   —   4 tests (domain entities)
```

Phase 1-G added 18 new tests (13 service, 5 API) for improvement simulation. All 175 pre-existing tests continued to pass.

> **Note.** These test results were reported during implementation and verified during the Phase 1-G verification review. The tests were not re-run during this documentation-only update. Run `python -m pytest --tb=short` to obtain current results.

---

## Known gaps requiring attention

1. **CSV bulk import**: No implementation. SYSTEM_REQUIREMENTS_COMPLETE.md identifies this as FR2, while the detailed SPECIFICATION.md identifies marks import as FR3 and uses FR2 for recording/updating marks. Resolve requirement numbering before final traceability sign-off. Implementing import also requires authenticated school access and durable import/approval audit records, which are not currently available and would require an approved persistence migration.
2. **Authentication / RBAC**: Authentication and role/scope checks are implemented in the current API, with targeted authorization tests. Production deployment security and browser-driven authorization flows remain unverified; see the latest implementation/testing report.
3. **Report generation**: Stub only in `domain_services.py`. No API endpoints for CSV/PDF export.
4. **Frontend verification**: A React/TypeScript frontend exists, including the university application review screen. Type-check and production build passed in the latest verification; browser-based end-to-end testing has not been performed.
5. **Performance baseline**: No load or response-time tests exist.
6. **Requirement identifier mismatch**: SYSTEM_REQUIREMENTS_COMPLETE.md and the detailed SPECIFICATION.md assign different meanings to FR9, FR11, FR12, FR13, and NFR14. The detailed specification does not define the requested FR13 staleness behavior; do not mark it complete until its intended rule and source document are confirmed.
7. **Required-subject check in domain_services.py**: `RequirementMatcher.check_subject_requirements` is a stub (`return bool(marks)`). This class is **not** wired to the production API path; the correct implementation lives in `UniversityProgramme.meets_subject_requirements()`. The stub should be updated if `RequirementMatcher` is ever wired to production routes.
8. **REQ-005 formal specification entry**: REQ-005 (improvement simulation) does not appear in the approved SPECIFICATION.md or SRD. It should be formally added to those documents before it can be treated as a fully approved requirement.
