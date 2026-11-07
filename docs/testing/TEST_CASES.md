# Assignment 5 — Test Case Development (UniMatch)

**Purpose:** Validate functional and non-functional requirements from **SYSTEM_REQUIREMENTS_COMPLETE.md** (FR1–FR15, NFR1–NFR20) against the behaviour described in **Use_Case_Specifications.md**.

**Related:** [SPECIFICATION.md](../requirements/SPECIFICATION.md) v2.0 · [ASSIGNMENT5_REFLECTION.md](../academic-evidence/ASSIGNMENT5_REFLECTION.md)

> **Evidence note:** This is the original requirements-based assignment test
> matrix. Its expected results and blank “Actual Result”/“Status” fields are not
> evidence of a current test run, and some scenarios describe integrations that
> are not implemented. Use the
> [implementation and testing report](IMPLEMENTATION_TESTING_EVALUATION.md) for
> the latest executed results, delivered application-review behavior, and
> outstanding payment, malware-scanning, PostgreSQL, and browser-testing limitations.
> Focused learner-document tests now cover local persistence, file validation,
> school-scoped access, and auditable human review. They do not establish
> malware scanning or PostgreSQL migration behavior; see the implementation
> report for the exact results.

---

## 6. Test Cases

### 6.1 Functional Test Cases
 
| Test Case ID | Requirement ID | Description | Steps | Expected Result | Actual Result | Status |
|---|---|---|---|---|---|---|
| TC001 | FR1 | Create learner profile with valid data | 1. Login as Teacher. 2. Navigate to Learners → Add new. 3. Enter all required fields. 4. Save. | Profile created. Confirmation shown. Audit log records teacher ID, action type, timestamp. | — | — |
| TC002 | FR1 | Save learner with missing school ID | 1. Login as Teacher. 2. Open Add Learner form. 3. Leave school ID blank. 4. Click Save. | Save blocked. School ID field highlighted red. Inline error message shown. | — | — |
| TC003 | FR2 | Import valid 100-row learner marks CSV | 1. Login as Teacher. 2. Navigate to Import Marks. 3. Upload correctly formatted CSV (100 rows). 4. Confirm. | Import summary: 100 imported, 0 errors. Marks visible on learner profiles. | — | — |
| TC004 | FR2 | Import CSV with mark value of 150 (out of range) | 1. Login as Teacher. 2. Upload CSV with one row where mark = 150. 3. Review preview. 4. Confirm. | Invalid row flagged in preview. Remaining 99 rows imported. Error report lists the offending row with reason. | — | — |
| TC005 | FR3, FR4 | Generate AI recommendations with explanation factors | 1. Login as Teacher. 2. Open learner with 7 subject marks. 3. Click "Generate recommendations." | Ranked list displayed within 3 seconds. Each programme shows: eligibility category + contributing factors (e.g., "Mathematics meets requirement; Physical Science below minimum"). | — | — |
| TC006 | FR3, FR4 | Verify recommendation categories match APS rules | 1. Configure a test learner with APS = 42. 2. Generate recommendations. 3. Verify categorisation against configured rules. | All programmes with minimum APS ≤ 42 and matching subjects appear as Guaranteed or Likely. Accuracy matches configured rules for the test dataset. | — | — |
| TC007 | FR5 | University Admissions records Accepted decision | 1. Login as University Admissions. 2. Open submitted application. 3. Select Accept. 4. Confirm. | Status updates to "Accepted." Audit trail records: old status, new status, officer ID, timestamp. Learner notification triggered. | — | — |
| TC008 | FR5 | Application lifecycle: Draft → Submitted | 1. Learner adds programme (Draft). 2. Pays fee (Fee Paid). 3. Teacher compiles package (Package Ready). 4. Learner submits (Submitted). | Each status transition occurs correctly. No step allows skipping to Submitted without fee paid and package ready. | — | — |
| TC009 | FR6 | Upload and review a valid PDF recommendation letter | 1. Login as SchoolAdmin or scoped Teacher. 2. Open a learner profile. 3. Upload a PDF and optionally link it to an application. 4. Download and manually review it. 5. Record a verification decision and note. | File and metadata are stored locally; status starts `PendingReview`; review identity, timestamp, and note are retained. The file remains `NotScanned`; no antivirus result is implied. PostgreSQL persistence requires migration 0008 and is not yet verified. | — | — |
| TC010 | FR6 | Attempt to upload unsupported or mismatched file content | 1. Login as SchoolAdmin or scoped Teacher. 2. Open a learner profile. 3. Upload an unsupported extension or content that does not match the declared PDF/DOC/DOCX type. | API rejects the upload with HTTP 422 and no document file is stored. | — | — |
| TC011 | FR7 | Dashboard loads within 2 seconds | 1. Login as Administrator. 2. Navigate to dashboard. 3. Record load time. | Dashboard loads ≤ 2 seconds. Status breakdown chart, deadlines list, missing documents count all rendered. | — | — |
| TC012 | FR10 | Learner cannot access Teacher management features | 1. Login as Learner. 2. Attempt to navigate to /learners/manage. | HTTP 403 returned. Learner redirected to own dashboard. No learner management UI visible. | — | — |
| TC013 | FR11 | DoE analytics contains no personally identifiable data | 1. Login as DoE Official. 2. View analytics dashboard and inspect all data fields. 3. Export CSV and inspect columns. | No names, ID numbers, or contact details visible anywhere. Only aggregated counts and percentages. CSV export contains no PII columns. | — | — |
| TC014 | FR8 | Learner receives notification on admission decision | 1. University Admissions records Accepted decision. 2. Check learner's notification feed and registered email. | Learner receives in-app notification: "Your application to [Programme] at [University] has been accepted." Email notification also received if configured. | — | — |
| TC015 | FR10 | Application submission blocked without fee payment | 1. Login as Learner. 2. Navigate to application with status "Draft." 3. Attempt to click "Submit application." | Submit button is disabled. Tooltip or message: "Complete fee payment before submitting." | — | — |
| TC016 | FR15 | Audit log captures full action context | 1. Login as Teacher. 2. Create learner. 3. Upload document. 4. Login as Administrator. 5. View Audit Log. | Both actions appear with: action type, acting user ID, affected record ID, old value, new value, timestamp. | — | — |
| TC017 | New — UC2 | University Admissions publishes a new programme | 1. Login as University Admissions. 2. Navigate to My Programmes → Add new. 3. Enter all required fields. 4. Publish. | Programme saved as active. Immediately available in learner programme explorer and AI recommendation engine. Version history entry created. | — | — |
 
### 6.2 Non-Functional Test Cases
 
| Test Case ID | Requirement ID | Description | Steps | Expected Result | Actual Result | Status |
|---|---|---|---|---|---|---|
| TC-NFR01 | NFR17, NFR19 | Performance: 500 concurrent users on dashboard | 1. Configure 500 virtual authenticated users in k6 or JMeter. 2. All navigate to dashboard simultaneously. 3. Run test for 5 minutes. 4. Record p95 response time and error rate. | Dashboard responds ≤ 2 seconds for ≥ 95% of requests (p95). No HTTP 5xx errors. Response time degradation < 5% vs single-user baseline. | — | — |
| TC-NFR02 | NFR13, NFR14 | Security: encryption in transit and RBAC enforced | 1. Inspect network traffic during login — verify TLS 1.3. 2. Call `GET /api/learners` without Authorization header. 3. Login as Administrator — verify MFA prompt appears. 4. Confirm sensitive DB fields encrypted at rest. | All traffic over TLS 1.3 exclusively. Unauthenticated API call returns HTTP 401. Admin login triggers MFA step. Sensitive fields AES-256 encrypted. | — | — |
| TC-NFR03 | NFR13 | Payment security: UniMatch does not store card details | 1. Complete a test payment flow. 2. Inspect UniMatch database and application logs after payment. | No card numbers, CVV, or full bank account details exist anywhere in UniMatch's database or logs. Only the payment gateway reference number is stored. | — | — |
| TC-NFR04 | NFR20 | Bulk CSV import: 1,000 records within 60 seconds | 1. Prepare valid 1,000-row CSV. 2. Login as Teacher. 3. Upload and confirm import. 4. Record wall-clock time to import summary. | Import completes ≤ 60 seconds. All 1,000 records saved correctly. No data corruption or partial imports. | — | — |
| TC-NFR05 | NFR18 | AI recommendation generation within 3 seconds | 1. Login as Teacher. 2. Open learner with 7 subjects. 3. Click "Generate recommendations." 4. Record time to ranked list display. | Results appear ≤ 3 seconds. Validated across 5 consecutive runs on the same learner profile. | — | — |
 
---

## 7. Implemented Extensions (added during implementation phase)

> The test cases in this section cover features that were **not part of the original Assignment 5 specification**. They were added during the implementation and testing phase following the project's own gap analysis and subsequent task instructions. They are separated from the original test cases (§6) to preserve the integrity of the submitted Assignment 5 evidence.

### 7.1 Improvement Simulation (FR-13 extension)

**Feature source:** Project gap analysis identified in TRACEABILITY.md; implemented Phase 1-G (2026-10-20).  
**Closest approved requirement:** SPECIFICATION.md §3.4 FR-13 ("The system shall compare learner marks and APS score to each programme's minimum requirements").  
**Provisional tracking ID:** REQ-005 (not in the approved specification — see TRACEABILITY.md REQ-NNN note).  
**Implementation:** `LearnerProfileService.simulate_eligibility`; `POST /api/learners/{learner_id}/simulate-eligibility`.  
**Test suite:** `tests/services/test_services.py::TestSimulateEligibility` (13 automated tests); `tests/api/test_api.py::TestSimulateEligibilityEndpoint` (5 automated tests). All pass as of 2026-10-20.

| Test Case ID | Related to | Description | Automated test | Expected Result | Actual Result | Status |
|---|---|---|---|---|---|---|
| TC018 | FR-13 ext. | Mark improvement raises APS and changes eligibility category | `TestSimulateEligibility::test_improvement_changes_aps_and_eligibility` | Simulated APS increases; eligibility improves; stored marks unchanged | Pass | PASS |
| TC019 | FR-13 ext. | Simulated mark below compulsory subject threshold → NotEligible | `TestSimulateEligibility::test_override_below_compulsory_subject_threshold` | NotEligible returned; `subject_requirements_checked=True` | Pass | PASS |
| TC020 | FR-13 ext. | Required subject absent from stored marks supplied via override | `TestSimulateEligibility::test_missing_compulsory_subject_supplied_via_override` | Subject requirement satisfied; eligibility classified on APS | Pass | PASS |
| TC021 | FR-13 ext. | University-specific scoring rule applied when registered | `TestSimulateEligibility::test_university_rule_applied_when_registered` | University APS used; `university_rule_applied=True` | Pass | PASS |
| TC022 | FR-13 ext. | NSC default formula used when no rule registered | `TestSimulateEligibility::test_nsc_fallback_when_no_rule_registered` | NSC APS used; `university_rule_applied=False` | Pass | PASS |
| TC023 | FR-13 ext. | Non-existent learner returns 404 | `TestSimulateEligibilityEndpoint::test_simulate_nonexistent_learner_returns_404` | HTTP 404 | Pass | PASS |
| TC024 | FR-13 ext. | Non-existent programme returns 404 | `TestSimulateEligibilityEndpoint::test_simulate_nonexistent_programme_returns_404` | HTTP 404 | Pass | PASS |
| TC025 | FR-13 ext. | Invalid override score (>100 or <0) rejected | `TestSimulateEligibilityEndpoint::test_simulate_invalid_override_score_returns_422` | HTTP 422; request rejected before reaching service | Pass | PASS |
| TC026 | FR-13 ext. | Stored marks unchanged after simulation | `TestSimulateEligibility::test_stored_marks_unchanged_after_successful_simulation` | Stored mark IDs and scores identical before and after call | Pass | PASS |
| TC027 | FR-13 ext. | No repository writes during simulation | `TestSimulateEligibility::test_no_repository_write_occurs` | Record counts in all repos identical before and after | Pass | PASS |
| TC028 | FR-13 ext. | Response carries `is_simulation: true` flag | `TestSimulateEligibilityEndpoint::test_simulate_improves_eligibility_and_returns_simulation_flag` | `is_simulation` field present and equals `true` in response body | Pass | PASS |
| TC029 | FR-13 ext. | API simulation uses registered university-specific scoring rule | `TestSimulateEligibilityEndpoint::test_simulate_uses_registered_university_scoring_rule` | University rule is applied; response marks result as simulated | Not run; test execution was denied | NOT RUN |

---