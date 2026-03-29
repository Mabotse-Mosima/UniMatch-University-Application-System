# Assignment 5 — Test Case Development (UniMatch)

**Purpose:** Validate functional and non-functional requirements from **SYSTEM_REQUIREMENTS_COMPLETE.md** (FR1–FR15, NFR1–NFR20) against the behaviour described in **Use_Case_Specifications.md**.

**Related:** [SPECIFICATION.md](SPECIFICATION.md) v2.0 · [ASSIGNMENT5_REFLECTION.md](ASSIGNMENT5_REFLECTION.md)

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
| TC009 | FR6 | Upload valid 2 MB PDF recommendation letter | 1. Login as Teacher. 2. Open learner → Documents. 3. Upload 2 MB PDF. 4. Select document type. 5. Confirm. | File stored. Document appears in list with filename, upload date, and uploader name. Metadata saved to Documents table. | — | — |
| TC010 | FR6 | Attempt to upload unsupported file type (.jpg) | 1. Login as Teacher. 2. Navigate to Documents. 3. Attempt to upload .jpg. | System rejects file. Message: "Only PDF, DOC, and DOCX files are accepted." Nothing stored. | — | — |
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