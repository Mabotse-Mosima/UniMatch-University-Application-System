# Assignment 6: Agile User Stories, Backlog, and Sprint Planning

**System**: UniMatch – School-Based University Application & Eligibility System  
**Author**: Christinah Mmabotse Mosima  
**Date**: 2026-04-03  
**Assignment**: 6 – Agile Planning  
**Builds on**:
- `SPECIFICATION.md` v2.0
- `SYSTEM_REQUIREMENTS_COMPLETE.md` (FR1–FR15, NFR1–NFR20)
- `USE_CASE_SPECIFICATIONS.md` (UC1–UC15)
- `TEST_CASES.md` (TC001–TC017, TC-NFR01–TC-NFR05)
- `STAKEHOLDER_ANALYSIS.md`
- `ARCHITECTURE.md` v2.0

---

## Table of Contents

1. [Scrum Roles and GitHub Tooling](#1-scrum-roles-and-github-tooling)
2. [User Stories](#2-user-stories)
3. [Product Backlog](#3-product-backlog)
4. [Sprint 1 Plan](#4-sprint-1-plan)
5. [Traceability Matrix](#5-traceability-matrix)
6. [Reflection](#6-reflection)

---

## 1. Scrum Roles and GitHub Tooling

Since UniMatch is an individual academic project, all three Scrum roles are performed by one person. In a production team, these roles are held by different people and form the core of a self-organising Scrum team.

| Scrum Role | Responsibilities | Played By |
|---|---|---|
| **Product Owner** | Writes and prioritises user stories, sets acceptance criteria, makes scope trade-off decisions, maintains the product backlog | Christinah Mmabotse Mosima |
| **Scrum Master** | Facilitates sprint planning and retrospective, enforces Definition of Done, tracks velocity, removes blockers | Christinah Mmabotse Mosima |
| **Developer** | Estimates story points, breaks stories into tasks, implements features, writes tests, closes GitHub Issues | Christinah Mmabotse Mosima |

### 1.1 GitHub Agile Tooling

| Tool | Usage |
|---|---|
| **GitHub Issues** | One issue per user story and one per task, each labelled with MoSCoW priority and story point estimate |
| **GitHub Projects (Board)** | Columns: `📋 Backlog` → `🔲 To Do` → `🔄 In Progress` → `👀 In Review` → `✅ Done` |
| **GitHub Milestones** | `Sprint 1 — MVP Core`, `Sprint 2 — Learner & Payment Flows`, `Sprint 3 — Decisions & Analytics` |
| **Labels** | `must-have`, `should-have`, `could-have`, `won't-have`, `bug`, `security`, `performance`, `SP:2`, `SP:3`, `SP:5`, `SP:8` |

### 1.2 Issue Templates

**User story template** (`.github/ISSUE_TEMPLATE/user_story.md`):

```markdown
## User Story
As a [role], I want [action] so that [benefit].

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2

## Metadata
| Field | Value |
|---|---|
| Story ID | US-XXX |
| MoSCoW | Must-have / Should-have / Could-have |
| Story Points | X |
| FR Trace | FR-X |
| UC Trace | UC-X |
| TC Trace | TC-XXX |
| Sprint | Sprint X / Backlog |
| Depends on | #issue-number |
```

---

## 2. User Stories

### 2.1 INVEST Criteria

Every story below satisfies all six INVEST criteria:

| Criterion | How enforced |
|---|---|
| **Independent** | Each story delivers a self-contained, demonstrable outcome. Dependencies noted in the backlog but do not make stories inseparable. |
| **Negotiable** | Acceptance criteria define the *what*, not the *how*. No implementation technology is prescribed inside a story. |
| **Valuable** | Every story names a real actor from `USE_CASE_SPECIFICATIONS.md §2.1` and states a benefit linked to a pain point in `STAKEHOLDER_ANALYSIS.md`. |
| **Estimable** | All stories are sized. Any story that could not be estimated was split until it could be. |
| **Small** | No story exceeds 8 story points. Large use cases (UC5, UC8) are split across multiple stories. |
| **Testable** | Every acceptance criterion maps to a test case in `TEST_CASES.md` or defines a new measurable condition. |

---

### 2.2 Authentication and Access Control

*Source: FR10, FR15, NFR14, UC1, UC15 — Components: Auth Controller, User Management Controller*

| Story ID | User Story | Acceptance Criteria | Priority | Req. Ref | UC Ref |
|---|---|---|---|---|---|
| **US001** | As a **teacher**, I want to log in with my email and password so that I can securely access my assigned learners' data and application tools. | Valid credentials issue JWT session in ≤2 seconds. Three failed attempts locks account with clear error message. Unauthenticated routes return HTTP 401. Redirect to role-appropriate dashboard on success. | High | FR10, FR15 | UC1 |
| **US002** | As a **school administrator**, I want to create user accounts and assign roles so that each person only accesses the features and data their role permits. | Admin can create accounts for all 7 role types (Teacher, Admin, Learner, Parent, University Admissions, DoE, IT). Role assignment takes effect immediately. HTTP 403 returned for unauthorised route access. Account creation audit-logged. | High | FR10, FR15 | UC1, UC15 |
| **US003** | As a **school IT support officer**, I want multi-factor authentication enforced on Administrator and IT accounts so that privileged access is protected against credential theft. | MFA OTP prompt appears after correct password for Admin/IT roles. Login blocked without valid OTP within 5 minutes. Standard roles (Teacher, Learner, Parent) use password only. | High | NFR14 | UC1, UC15 |

---

### 2.3 Learner Profile and Marks Management

*Source: FR1, FR2, FR14, UC3, UC4 — Components: Learner Controller, Repository Layer*

| Story ID | User Story | Acceptance Criteria | Priority | Req. Ref | UC Ref |
|---|---|---|---|---|---|
| **US004** | As a **teacher**, I want to create and update learner profiles with name, ID number, grade, and subject choices so that I have a complete and verified academic record for each learner. | Profile saves with all mandatory fields validated. Duplicate ID numbers rejected with 409 error. Audit log entry created on every change (action, actor, record ID, timestamp). | High | FR1 | UC3 |
| **US005** | As a **teacher**, I want to record and update subject marks for each learner so that the system has accurate data for eligibility calculations. | Marks saved per subject with score (0–100), exam type, and year. Existing marks updatable. Invalid scores (>100 or <0) rejected with inline error per TC004 pattern. Changes logged in audit trail. | High | FR1 | UC3, UC4 |
| **US006** | As a **teacher**, I want to import learner marks from a CSV file so that I do not have to manually enter data for an entire class at the start of each term. | CSV validated before import. Preview shown before confirming. Out-of-range values flagged per TC004. Import summary: imported, skipped, errors. Completes ≤60 seconds for 1,000 records (NFR20). | High | FR2 | UC4 |
| **US010** | As a **teacher**, I want to apply a grade promotion or counselor change to multiple learners at once so that I do not have to edit each learner record individually at year-start. | Teacher selects multiple learners via checkboxes. Bulk actions available: update grade, change counselor. Each individual change audit-logged. | Low | FR14 | UC3 |

---

### 2.4 University Programme Management

*Source: UC2, SPECIFICATION §3.3 — Components: Application Controller, Repository Layer*

| Story ID | User Story | Acceptance Criteria | Priority | Req. Ref | UC Ref |
|---|---|---|---|---|---|
| **US007** | As a **university admissions officer**, I want to publish and maintain verified programme information — including APS requirements, deadlines, fees, and required documents — so that learners and teachers see accurate data when making application decisions. | Officer can add, edit, and deactivate programmes. Published programmes immediately visible in learner programme explorer and AI recommendation engine. Version history entry created per TC017. Past-deadline publications trigger confirmation warning. | High | FR3, FR4 | UC2 |

---

### 2.5 AI Recommendation Engine

*Source: FR3, FR4, UC5 — Components: Recommendation Controller, ApsCalculator, RequirementMatcher, EligibilityClassifier (ARCHITECTURE.md §4–5)*

| Story ID | User Story | Acceptance Criteria | Priority | Req. Ref | UC Ref |
|---|---|---|---|---|---|
| **US008** | As a **teacher**, I want to generate AI-based eligibility recommendations for a learner so that I can guide them toward suitable university programmes using supporting evidence rather than manual calculations. | Recommendations appear within 3 seconds (NFR18). Each result shows eligibility category (Guaranteed / Likely / Borderline / Not Eligible). Classification accuracy >95% against configured APS rules per TC005, TC006, TC-NFR05. | High | FR3, FR4 | UC5 |
| **US009** | As a **teacher**, I want to see the specific factors that contributed to each recommendation so that I can have a meaningful, evidence-based guidance conversation with the learner rather than presenting an opaque score. | Every result shows: learner APS, programme minimum APS, contributing subjects, and unmet subject requirements. Explanation displayed inline — no extra navigation required per TC005 acceptance criteria. | High | FR3, FR4 | UC5, UC6 |

---

### 2.6 Guidance Session

*Source: UC6 — Component: Learner Controller (notes sub-resource)*

| Story ID | User Story | Acceptance Criteria | Priority | Req. Ref | UC Ref |
|---|---|---|---|---|---|
| **US011** | As a **teacher**, I want to record structured guidance session notes for each learner so that the school has a documented, auditable record of advice given and the learner's expressed preferences. | Teacher can record: topics discussed, risks flagged, alternatives suggested, learner preferences. Notes saved with counselor ID and timestamp. Teacher cannot alter system eligibility categories. Notes visible to admin but not to learner or parent. | Medium | FR1, FR5 | UC6 |

---

### 2.7 Learner Programme Selection

*Source: FR3, FR5, UC7 — Component: Application Controller*

| Story ID | User Story | Acceptance Criteria | Priority | Req. Ref | UC Ref |
|---|---|---|---|---|---|
| **US012** | As a **learner**, I want to browse verified university programmes sorted by my eligibility likelihood so that I can make an informed selection without relying on unverified agents or manual research. | Programme explorer shows programmes sorted by UC5 eligibility results. Filters available: university, faculty, deadline, fee range, eligibility category. Expired deadlines shown as disabled per UC7-AF1. | High | FR3, FR7 | UC7 |
| **US013** | As a **learner**, I want to add programmes to my application list so that I can manage all my university applications in one place. | Programme added to list with status "Draft." Duplicate additions prevented per UC7-AF3. Borderline/Not Eligible selection triggers warning — not blocked (learner autonomy preserved) per UC7-AF2. | High | FR3, FR5 | UC7 |

---

### 2.8 Fee Payment

*Source: UC8, NFR13 — Component: Payment Module (delegates to external gateway)*

| Story ID | User Story | Acceptance Criteria | Priority | Req. Ref | UC Ref |
|---|---|---|---|---|---|
| **US014** | As a **learner**, I want to pay official application fees through UniMatch via a certified payment gateway so that I eliminate the need for agents and am protected from payment fraud. | Fee amount matches published university data (UC2). Payment fully delegated to external gateway — UniMatch stores only payment reference (TC-NFR03 verified: no card data stored). Status updates to "Fee Paid" on confirmation. Payment confirmation notification sent. | High | FR7, NFR13 | UC8 |
| **US015** | As a **learner**, I want to be clearly informed if my payment fails or times out so that I do not accidentally make a duplicate payment. | AF1: declined payment shows clear message and keeps status "Draft." AF2: gateway timeout shows advisory message warning not to retry before checking bank statement per UC8-AF2. | High | UC8-AF1, UC8-AF2 | UC8 |

---

### 2.9 Application Package and Submission

*Source: FR5, FR6, UC9, UC10 — Components: Document Controller, Application Controller*

| Story ID | User Story | Acceptance Criteria | Priority | Req. Ref | UC Ref |
|---|---|---|---|---|---|
| **US016** | As a **teacher**, I want to upload recommendation letters and supporting documents for a learner so that their application package is complete and verified before submission. | PDF, DOC, DOCX accepted (TC010). File size limit enforced. Virus scan performed on upload. Metadata stored: filename, upload date, uploader name. Missing required documents flagged on package status. | High | FR6 | UC9 |
| **US017** | As a **learner**, I want to review my compiled application package before submitting so that I can confirm everything is correct and complete. | Learner views: academic transcript, personal info, supporting documents, recommendation letters. Read-only view — learner cannot edit documents. Missing documents listed per TC010 pattern. | High | FR5, FR6 | UC9, UC10 |
| **US018** | As a **learner**, I want to submit my application through UniMatch so that it is delivered securely to the university without me needing to use their separate portal. | Pre-submission checks enforced: fee confirmed, all required documents present, deadline not passed (TC008). University acknowledgement reference stored. Status → "Submitted." Confirmation notification sent to learner and teacher. University integration unavailable → application queued and retried automatically per UC10-AF3. | High | FR5 | UC10 |

---

### 2.10 University Admissions Decision

*Source: FR5, FR15, UC11 — Component: Application Controller*

| Story ID | User Story | Acceptance Criteria | Priority | Req. Ref | UC Ref |
|---|---|---|---|---|---|
| **US019** | As a **university admissions officer**, I want to review submitted applications and record an official admission decision so that learners and school staff are notified automatically and outcomes are tracked in one system. | Officer sees all submitted applications for their institution. Decision options: Accept / Reject / Waitlist / Request Additional Documents (with specific list). Decision logged with officer ID, timestamp, and optional note per TC007. Learner and teacher notified per TC014. Audit trail preserved per UC11-AF2. | High | FR5, FR15 | UC11 |

---

### 2.11 Status Tracking and Notifications

*Source: FR5, FR7, FR8, FR12, FR13, UC12, UC13*

| Story ID | User Story | Acceptance Criteria | Priority | Req. Ref | UC Ref |
|---|---|---|---|---|---|
| **US020** | As a **learner**, I want to track the real-time status of all my applications in one place so that I always know where each application stands without contacting universities individually. | Application tracker shows: current status per university, status history timeline, and pending actions. Status reflects correct lifecycle states. Loads ≤2 seconds per TC011. | High | FR5, FR7 | UC12 |
| **US021** | As a **teacher**, I want to receive automated deadline reminders when application deadlines are approaching so that I never miss a critical submission window for any learner. | Reminders dispatched at 7-day, 3-day, and 1-day thresholds per FR13. Each notification lists affected learners and outstanding items. Delivery logged. Retry mechanism on failure. | High | FR8, FR13 | UC13 |
| **US022** | As a **learner**, I want to receive a notification when my application status changes so that I am informed immediately without manually checking the system. | Notification appears in learner portal within 1 minute of a status change triggered by UC11 or UC10. Notification persists until read per TC014. | Medium | FR8 | UC12, UC13 |
| **US023** | As a **parent or guardian**, I want to receive notifications about key milestones in my child's application so that I can support them and stay informed without calling the school. | Parent notified for: submission confirmed, documents requested, admission decision received. No personal academic data included in notifications. | Medium | FR8, FR12 | UC13 |

---

### 2.12 Dashboards and Reporting

*Source: FR7, FR9, FR11, NFR15, UC14*

| Story ID | User Story | Acceptance Criteria | Priority | Req. Ref | UC Ref |
|---|---|---|---|---|---|
| **US024** | As a **teacher**, I want a dashboard showing my assigned learners' application statuses, upcoming deadlines, and flagged items so that I can prioritise my daily guidance tasks. | Dashboard loads ≤2 seconds per TC011. Shows: learner status summary by category, upcoming deadlines, "needs attention" flags (missing documents, overdue items). | High | FR7 | UC12 |
| **US025** | As a **school administrator**, I want to generate and export school-wide application reports as PDF or CSV so that I can meet compliance reporting requirements for school management and government submission. | Reports export as PDF or CSV with customisable date ranges per FR9. Generated within 60 seconds for standard datasets. No PII in DoE-format exports per TC013 pattern. | Medium | FR9, FR11 | UC14 |
| **US026** | As a **DoE / District Official**, I want to view anonymized aggregated analytics about application trends so that I can make evidence-based policy and resource allocation decisions. | No names, ID numbers, or contact details visible anywhere per TC013. Only aggregated counts and percentages. CSV export contains no PII columns. HTTP 403 on any individual learner endpoint. | Medium | FR11, NFR15 | UC14 |

---

### 2.13 Non-Functional User Stories

*Source: NFR13, NFR15, NFR16, NFR17, NFR19, NFR4, NFR6*

| Story ID | User Story | Acceptance Criteria | Priority | Req. Ref | TC Ref |
|---|---|---|---|---|---|
| **US027** | As a **school IT support officer**, I want all learner data encrypted with TLS 1.3 in transit and AES-256 at rest so that POPIA security requirements are met and data is protected against breach. | Network analysis confirms TLS 1.3 in use. HTTP redirects to HTTPS. Sensitive database fields encrypted per TC-NFR02. No plaintext PII in logs. | High | NFR13 | TC-NFR02 |
| **US028** | As a **school IT support officer**, I want a complete audit log of all user actions so that I can investigate security incidents and demonstrate regulatory compliance. | Every action logged: user ID, action type, affected record ID, old and new values, timestamp per TC016. Log viewable by Admin and IT Support roles only. | High | FR15, NFR16 | TC016 |
| **US029** | As a **learner**, I want to be certain that UniMatch never stores my card details so that my financial information is always protected. | End-to-end test of payment flow confirms no card numbers, CVV, or bank account details exist anywhere in UniMatch's database or logs per TC-NFR03. Only payment gateway reference stored. | High | NFR13 | TC-NFR03 |
| **US030** | As a **teacher**, I want the system to remain responsive during peak school hours so that I can complete tasks efficiently without performance disruptions. | Dashboard responds ≤2 seconds for ≥95% of requests under 500 concurrent users per TC-NFR01. Degradation <5% vs single-user baseline. No HTTP 5xx errors during load test. | High | NFR17, NFR19 | TC-NFR01 |

---

**Story count**: 30 stories total  
**FR coverage**: FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR8, FR9, FR10, FR11, FR12, FR13, FR14, FR15, NFR13, NFR14, NFR15, NFR16, NFR17, NFR19, NFR20  
**UC coverage**: UC1–UC15 (all use cases covered)  
**Satisfies**: "8+ from Assignment 4 FRs" and "4+ from Assignment 5 UCs" — exceeded on both counts

---

## 3. Product Backlog

### 3.1 Estimation Baseline

> **Baseline = 3 story points**: US004 — Create and update learner profiles. This requires one database migration, one REST endpoint (POST + PUT), one form UI with validation, and two unit tests. A single developer can complete it in approximately one focused working day. All other stories are estimated relative to this baseline using the Fibonacci sequence (1, 2, 3, 5, 8, 13).

### 3.2 MoSCoW Prioritized Backlog

> Story points reflect effort and complexity, not clock hours. A "5" is approximately double the effort of a "3."

| Story ID | User Story (summary) | Actor | MoSCoW | Story Points | Dependencies | Req. Ref |
|---|---|---|---|---|---|---|
| **US001** | Login with email and password | All | Must-have | 2 | None | FR10, FR15 |
| **US002** | Create accounts and assign roles | Admin | Must-have | 3 | US001 | FR10, FR15 |
| **US003** | MFA for Admin and IT accounts | IT Support | Must-have | 3 | US001, US002 | NFR14 | ⚠ Must-have deferred to Sprint 2 — depends only on US001/US002 but Sprint 1 is at capacity (29 pts). Auth is built in Sprint 1; MFA is the first Sprint 2 story so the privileged login path is hardened before any sensitive data volume accumulates. |
| **US004** | Create and update learner profiles | Teacher | Must-have | 3 | US001, US002 | FR1 |
| **US005** | Record and update subject marks | Teacher | Must-have | 2 | US004 | FR1 |
| **US006** | Import marks via CSV | Teacher | Must-have | 5 | US004, US005 | FR2 |
| **US007** | Publish and maintain programme catalogue | Univ. Admissions | Must-have | 5 | US001, US002 | FR3, FR4 |
| **US008** | Generate AI eligibility recommendations | Teacher | Must-have | 8 | US004, US005, US007 | FR3, FR4 |
| **US009** | Explanation factors per recommendation | Teacher | Must-have | 3 | US008 | FR3, FR4 |
| **US016** | Upload supporting documents | Teacher | Must-have | 3 | US004 | FR6 | ⚠ Must-have deferred to Sprint 2 — Sprint 1 is at capacity (29 pts). Document upload is architecturally required before submission (UC10 «includes» UC9) but has no dependency on the recommendation engine, making it safe to defer without blocking Sprint 1 stories. |
| **US024** | Teacher application dashboard | Teacher | Must-have | 5 | US004, US020 | FR7 |
| **US027** | TLS 1.3 + AES-256 encryption | IT Support | Must-have | 3 | US001 | NFR13 |
| **US028** | Complete audit log of all actions | IT Support | Must-have | 3 | US001, US002 | FR15, NFR16 |
| **US029** | No card data stored — gateway only | Learner | Must-have | 3 | US014 | NFR13 |
| **US030** | System responsive under 500 concurrent users | All | Must-have | 3 | All frontend | NFR17, NFR19 |
| **US012** | Browse programmes by eligibility | Learner | Should-have | 5 | US007, US008 | FR3, FR7 |
| **US013** | Add programmes to application list | Learner | Should-have | 3 | US012 | FR3, FR5 |
| **US014** | Pay application fee via gateway | Learner | Should-have | 8 | US013, US007 | FR7, NFR13 |
| **US015** | Clear payment failure and timeout messaging | Learner | Should-have | 2 | US014 | UC8-AF1, UC8-AF2 |
| **US017** | Review compiled package before submitting | Learner | Should-have | 3 | US016, US013 | FR5, FR6 |
| **US018** | Submit application through UniMatch | Learner | Should-have | 5 | US014, US017 | FR5 |
| **US019** | Review applications and record decisions | Univ. Admissions | Should-have | 5 | US018 | FR5, FR15 |
| **US020** | Track all application statuses | Learner | Should-have | 3 | US018, US019 | FR5, FR7 |
| **US021** | Automated deadline reminders to teachers | Teacher | Should-have | 5 | US024, US004 | FR8, FR13 |
| **US011** | Record guidance session notes | Teacher | Could-have | 3 | US008 | FR1, FR5 |
| **US022** | In-app status notifications (learner) | Learner | Could-have | 3 | US020, US019 | FR8 |
| **US023** | Milestone notifications for parents | Parent | Could-have | 3 | US022, US001 | FR8, FR12 |
| **US025** | Export school-wide reports PDF/CSV | Admin | Could-have | 5 | US024 | FR9, FR11 |
| **US026** | DoE anonymized analytics dashboard | DoE Official | Could-have | 5 | US025 | FR11, NFR15 |
| **US010** | Bulk update learner records | Teacher | Could-have | 3 | US004 | FR14 |

**Backlog point totals**:

| Priority | Stories | Story Points |
|---|---|---|
| Must-have | 15 | 51 |
| Should-have | 9 | 39 |
| Could-have | 6 | 22 |
| **Total** | **30** | **112** |

> **Note on totals**: The 112-point total represents the **full product backlog** — all stories across all sprints. Sprint 1 commits 29 of the 51 Must-have points. The remaining 83 points are distributed across Sprints 2, 3, and 4. This is correct Agile practice: the backlog is the complete scope of the product, not just what remains unstarted.

### 3.3 Won't-Have (This Release)

| Item | Reason deferred |
|---|---|
| NSFAS / full national funding integration | Requires external API agreements; explicitly out of scope in `SPECIFICATION.md §1.4` |
| Replacement of university backend systems | UniMatch coordinates and records — it is not a replacement admission system |
| Full legal POPIA certification | Conceptual compliance follows POPIA principles; formal certification is out of scope |
| Native iOS / Android mobile application | Web-first MVP; mobile PWA is a future enhancement |
| Advanced ML recommendation model trained on historical data | Rule-based APS engine is sufficient and testable for MVP; ML deferred to future version |

### 3.4 Backlog Prioritization Justification

**Must-have (15 stories, 51 points)** form the irreducible core. Without authentication and RBAC (US001–003), the system cannot safely serve any actor. Without learner profiles and marks (US004–006), the recommendation engine has no inputs. Without the programme catalogue (US007), the engine has nothing to compare against. The recommendation engine itself (US008–009) is the system's primary value proposition — a teacher cannot guide a learner without it. Document upload (US016) and the teacher dashboard (US024) complete the minimum viable staff workflow. Security foundations (US027–030) are Must-have because deploying a system holding minors' academic data without encryption, audit logging, and payment safety is ethically indefensible regardless of project scope. This aligns with the stakeholder success metrics in `STAKEHOLDER_ANALYSIS.md` and NFR13–NFR17.

**Should-have (9 stories, 39 points)** deliver the full learner-facing journey: programme selection, fee payment, package review, submission, university decision recording, status tracking, and deadline notifications. These are the flows that transform UniMatch from a school administrative tool into the coordination platform described in `SPECIFICATION.md v2.0`. They are not blocking the Phase 1 MVP but represent the target vision for Phase 2 (Sprint 2 and Sprint 3).

**Could-have (6 stories, 22 points)** enhance specific actor experiences. Guidance session notes (US011) improve the quality of teacher–learner interactions. Learner and parent notifications (US022–023) close the communication loop. Government analytics (US025–026) address the DoE and District stakeholder concerns from `STAKEHOLDER_ANALYSIS.md` but are not critical for day-one school operations.

---

## 4. Sprint 1 Plan

### 4.1 Sprint Goal

> **"Establish the secure, authenticated foundation of UniMatch: teachers can log in, manage learner profiles, import marks, and generate AI eligibility recommendations with transparent explanation factors — delivering the core staff workflow that all subsequent platform features depend on."**

This sprint covers Phase 1 of `SPECIFICATION.md §1.4` and deliberately de-risks the highest-complexity component (the recommendation engine, US008) early in the project lifecycle. Every selected story is a Must-have with no dependencies on unbuilt features.

### 4.2 Sprint Details

| Field | Detail |
|---|---|
| **Sprint Number** | 1 |
| **Duration** | 2 weeks (14 calendar days) |
| **Start Date** | 2026-04-06 |
| **End Date** | 2026-04-19 |
| **GitHub Milestone** | `Sprint 1 — MVP Core (Phase 1)` |
| **Velocity Target** | 29 story points |
| **Capacity** | 1 developer × 7 focused hours/day × 14 days = 98 hours (4 hours reserved for planning, standups, retrospective) |

### 4.3 Definition of Done

A story is Done when **all** of the following are true:

- [ ] All tasks for the story are marked complete
- [ ] Unit and integration tests pass with zero failures
- [ ] Acceptance criteria manually verified against the test case table
- [ ] Code pushed to a feature branch and merged to main via PR
- [ ] GitHub Issue closed and linked to the Sprint 1 milestone
- [ ] Any new API endpoint documented in `docs/api/README.md`
- [ ] Any new environment variables added to `.env.example`

### 4.4 Sprint 1 Selected Stories

| Story ID | User Story Summary | Story Points | Why Selected |
|---|---|---|---|
| **US001** | Login with email and password | 2 | Every feature depends on authentication — impossible to build or test anything without it |
| **US002** | Create user accounts and assign roles | 3 | RBAC required before any protected route can be tested |
| **US004** | Create and update learner profiles | 3 | Core data entity; all downstream features (UC5, UC9, UC10) operate on learner records |
| **US005** | Record and update subject marks | 2 | Required input for the recommendation engine |
| **US007** | Publish and maintain programme catalogue | 5 | Engine needs programme data to compare against — cannot de-risk US008 without this |
| **US008** | Generate AI eligibility recommendations | 8 | Primary value proposition; highest technical risk — de-risked early in Sprint 1 |
| **US009** | Explanation factors per recommendation | 3 | Inseparable UX complement to US008; addresses TC005 acceptance criteria |
| **US027** | TLS 1.3 + AES-256 encryption | 3 | Security is built in from day 1 — encryption cannot be retrofitted to already-stored data |
| **TOTAL** | | **29 pts** | Within capacity target |

### 4.5 Sprint 1 Task Breakdown

All tasks assigned to: **Christinah Mmabotse Mosima**  
Component names match `ARCHITECTURE.md §4` (C4 Level 3 Backend API Components).

---

#### US001 — Authentication (2 points)

| Task ID | Task Description | Component | Est. Hours | Status |
|---|---|---|---|---|
| T001 | Initialise Node.js/Express project: folder structure, `.env`, PostgreSQL connection pool | Backend / DevOps | 3 | To Do |
| T002 | Design and migrate `users` table: id, email, password_hash, role, mfa_secret, failed_attempts, locked_until, created_at | Repository Layer | 2 | To Do |
| T003 | Implement `POST /auth/login`: validate credentials (bcrypt), issue JWT (15-min access + refresh token), enforce 3-failure account lock | Auth Controller | 4 | To Do |
| T004 | Implement JWT validation middleware — attach `req.user` with role on every protected route | Auth Controller | 2 | To Do |
| T005 | Build React login page: email/password form, error display, redirect to role-appropriate dashboard | React Frontend | 3 | To Do |
| T006 | Unit tests: valid login → 200 + token; wrong password → 401; unknown email → 401; 3 failures → lock | Auth Controller tests | 2 | To Do |

---

#### US002 — User Role Management (3 points)

| Task ID | Task Description | Component | Est. Hours | Status |
|---|---|---|---|---|
| T007 | Define role enum in DB: Teacher, Admin, Learner, Parent, UniAdmissions, DoE, IT | Repository Layer | 1 | To Do |
| T008 | Implement `requireRole(...roles)` middleware — returns HTTP 403 if role not permitted | Express middleware | 3 | To Do |
| T009 | Implement `POST /admin/users` and `PATCH /admin/users/:id/role` with audit log entry on each change | User Management Controller | 3 | To Do |
| T010 | Build Admin UI: user list table, create user form (email, name, role dropdown), edit role action | React Frontend (Admin) | 4 | To Do |
| T011 | Integration tests: Teacher blocked from `/admin/` (403); DoE blocked from `/learners/` (403); Admin creates and updates roles | RBAC tests | 2 | To Do |

---

#### US004 — Learner Profile (3 points)

| Task ID | Task Description | Component | Est. Hours | Status |
|---|---|---|---|---|
| T012 | Design and migrate `learners` table: id, full_name, id_number, grade, school_id, counselor_id, status, created_at, updated_at | Repository Layer | 2 | To Do |
| T013 | Implement `POST /learners` and `PUT /learners/:id` with full field validation and duplicate id_number check (returns 409) | Learner Controller | 3 | To Do |
| T014 | Build Add/Edit Learner form UI (React): all fields, required-field validation, duplicate ID error, success toast | React Frontend (Staff) | 4 | To Do |
| T015 | Implement audit log write on every create/update: action_type, user_id, record_id, changed_fields, timestamp | Repository Layer | 2 | To Do |
| T016 | Unit tests per TC001 (valid create → 201), TC002 (missing school_id → 400), duplicate id_number → 409 | Learner Controller tests | 2 | To Do |

---

#### US005 — Subject Marks (2 points)

| Task ID | Task Description | Component | Est. Hours | Status |
|---|---|---|---|---|
| T017 | Design and migrate `subjects` and `marks` tables: marks(id, learner_id, subject_id, score, exam_type, year) | Repository Layer | 1 | To Do |
| T018 | Implement `POST /learners/:id/marks` and `PUT /marks/:id` with score range validation (0–100) | Learner Controller | 3 | To Do |
| T019 | Build marks entry UI: subject dropdown + score input within learner profile | React Frontend | 3 | To Do |
| T020 | Unit tests: save marks → 201; update marks → 200; score = 150 → 400 per TC004 pattern | Learner Controller tests | 2 | To Do |

---

#### US007 — Programme Catalogue (5 points)

| Task ID | Task Description | Component | Est. Hours | Status |
|---|---|---|---|---|
| T021 | Design and migrate `universities` and `programmes` tables: min_aps, subject_requirements (JSONB), fee, deadline, required_documents | Repository Layer | 2 | To Do |
| T022 | Implement CRUD API: `POST /programmes`, `PUT /programmes/:id`, `DELETE /programmes/:id` (soft delete — sets active = false) | Application Controller | 4 | To Do |
| T023 | Build University Admissions UI: programme list, add/edit form, publish/deactivate toggle | React Frontend (University) | 5 | To Do |
| T024 | Seed database with 10 South African university programme records for test and demo use | DevOps / Test data | 2 | To Do |
| T025 | Unit tests per TC017: publish programme → immediately visible in learner explorer and recommendation engine | Application Controller tests | 2 | To Do |

---

#### US008 — AI Recommendation Engine (8 points)

| Task ID | Task Description | Component | Est. Hours | Status |
|---|---|---|---|---|
| T026 | Implement `ApsCalculator` service: sum top N subjects per South African APS formula, configurable N | Recommendation Engine Service | 4 | To Do |
| T027 | Implement `RequirementMatcher` service: compare learner APS and subject levels against all active programmes | Recommendation Engine Service | 5 | To Do |
| T028 | Implement `EligibilityClassifier`: assign Guaranteed / Likely / Borderline / Not Eligible per configured thresholds | Recommendation Engine Service | 3 | To Do |
| T029 | Implement `POST /learners/:id/recommendations` endpoint — orchestrates engine, saves result with timestamp | Recommendation Controller | 3 | To Do |
| T030 | Unit tests per TC006: APS = 42 learner → correct categories; classification accuracy matches configured rules | Recommendation Engine tests | 4 | To Do |

---

#### US009 — Recommendation Explanation Factors (3 points)

| Task ID | Task Description | Component | Est. Hours | Status |
|---|---|---|---|---|
| T031 | Extend `RequirementMatcher` to capture and return per-result explanation: learner APS, programme minimum, contributing subjects, unmet subject requirements | Recommendation Engine Service | 3 | To Do |
| T032 | Build recommendations results UI (React): ranked list, eligibility category badge, APS comparison panel, collapsible explanation per programme | React Frontend (Staff) | 5 | To Do |
| T033 | Unit tests per TC005: explanation factors present for all results; unmet subjects correctly identified | Recommendation Engine tests | 2 | To Do |

---

#### US027 — Security Foundation (3 points)

| Task ID | Task Description | Component | Est. Hours | Status |
|---|---|---|---|---|
| T034 | Configure HTTPS with TLS 1.3 on Express server; add HTTP → HTTPS redirect middleware | Backend / DevOps | 2 | To Do |
| T035 | Implement `EncryptionService` using AES-256-CBC; apply to sensitive DB columns on write and read (key stored in `.env`) | Repository Layer | 3 | To Do |
| T036 | Security tests per TC-NFR02: verify TLS 1.3 in use via `openssl s_client`; unauthenticated API call returns 401; raw DB row shows ciphertext not plaintext | Security tests | 2 | To Do |

---

### 4.6 Sprint 1 Capacity Summary

| User Story | Story Points | Estimated Hours |
|---|---|---|
| US001 — Authentication | 2 | 16 |
| US002 — Role Management | 3 | 13 |
| US004 — Learner Profile | 3 | 13 |
| US005 — Subject Marks | 2 | 9 |
| US007 — Programme Catalogue | 5 | 15 |
| US008 — Recommendation Engine | 8 | 19 |
| US009 — Explanation Factors | 3 | 10 |
| US027 — Security Foundation | 3 | 7 |
| **TOTAL** | **29 pts** | **102 hours** |

> Solo developer capacity: 7 focused hours/day × 14 days = 98 hours. The 4-hour buffer is absorbed by shared database migrations (T012 for US004 is reused by US005) and shared engine instantiation (T026 shared by US008 and US009). Sprint ceremonies estimated at 4 hours total.

### 4.7 GitHub Project Board at Sprint Start

```
📋 BACKLOG        | 🔲 TO DO (Sprint 1) | 🔄 IN PROGRESS | 👀 IN REVIEW | ✅ DONE
──────────────────────────────────────────────────────────────────────────────────
US003 (MFA)       | US001               |                |              |
US006 (CSV)       | US002               |                |              |
US010 (bulk)      | US004               |                |              |
US011 (guidance)  | US005               |                |              |
US012 onwards...  | US007               |                |              |
                  | US008               |                |              |
                  | US009               |                |              |
                  | US027               |                |              |
```

### 4.8 Sprint 2 Preview

| Story | Summary | Points |
|---|---|---|
| US003 | MFA for Admin/IT accounts ⚠ Must-have deferred from Sprint 1 | 3 |
| US006 | CSV marks import | 5 |
| US010 | Bulk update learner records | 3 |
| US016 | Upload supporting documents ⚠ Must-have deferred from Sprint 1 | 3 |
| US012 | Browse programmes (learner portal) | 5 |
| US013 | Add programmes to application list | 3 |
| US014 | Pay application fee via gateway | 8 |
| US015 | Payment failure/timeout messaging | 2 |
| **Total** | | **32 pts** |

---

## 5. Traceability Matrix

Every story traces to at least one Assignment 4 requirement, one Assignment 5 use case, and one Assignment 5 test case.

| Story ID | A4 Requirement | A5 Use Case | A5 Test Case | MoSCoW | Sprint |
|---|---|---|---|---|---|
| US001 | FR10, FR15 | UC1 — Login & authenticate | TC012 | Must-have | Sprint 1 |
| US002 | FR10, FR15 | UC15 — Manage user roles & access | TC012, TC016 | Must-have | Sprint 1 |
| US003 | NFR14 | UC1, UC15 | TC-NFR02 | Must-have | Sprint 2 ⚠ Deferred from Sprint 1 due to capacity (Sprint 1 = 29 pts). MFA depends only on US001/US002 but adding it to Sprint 1 would exceed the 14-day solo capacity. Auth is completed in Sprint 1; MFA is the first committed Sprint 2 story. |
| US004 | FR1 | UC3 — Manage learner profile | TC001, TC002 | Must-have | Sprint 1 |
| US005 | FR1 | UC3, UC4 | TC004 | Must-have | Sprint 1 |
| US006 | FR2 | UC4 — Import learner marks via CSV | TC003, TC004 | Must-have | Sprint 2 |
| US007 | FR3, FR4 | UC2 — Publish programme information | TC017 | Must-have | Sprint 1 |
| US008 | FR3, FR4 | UC5 — Generate AI recommendations | TC005, TC006, TC-NFR05 | Must-have | Sprint 1 |
| US009 | FR3, FR4 | UC5, UC6 | TC005 | Must-have | Sprint 1 |
| US010 | FR14 | UC3 | — | Could-have | Sprint 3 |
| US011 | FR1, FR5 | UC6 — Conduct guidance session | — | Could-have | Sprint 3 |
| US012 | FR3, FR7 | UC7 — Select universities & programmes | TC015 | Should-have | Sprint 2 |
| US013 | FR3, FR5 | UC7 | TC015, TC012 | Should-have | Sprint 2 |
| US014 | FR7, NFR13 | UC8 — Pay application fee | TC-NFR03 | Should-have | Sprint 2 |
| US015 | UC8-AF1, UC8-AF2 | UC8 — Payment failure/timeout handling | TC-NFR01 | Should-have | Sprint 2 |
| US016 | FR6 | UC9 — Compile application package | TC009, TC010 | Must-have | Sprint 2 ⚠ Must-have deferred from Sprint 1 due to capacity. This is not a lower-priority decision — document upload is on the critical path to submission (UC10 «includes» UC9). Sprint 1 capacity is fully committed to auth + recommendation engine. |
| US017 | FR5, FR6 | UC9, UC10 | TC010 | Should-have | Sprint 2 |
| US018 | FR5 | UC10 — Submit application | TC008 | Should-have | Sprint 2 |
| US019 | FR5, FR15 | UC11 — Review & decide on application | TC007, TC016 | Should-have | Sprint 2 |
| US020 | FR5, FR7 | UC12 — Track application status | TC011 | Should-have | Sprint 2 |
| US021 | FR8, FR13 | UC13 — Receive notifications | — | Should-have | Sprint 2 |
| US022 | FR8 | UC12, UC13 | TC014 | Could-have | Sprint 3 |
| US023 | FR8, FR12 | UC13 | TC014 | Could-have | Sprint 3 |
| US024 | FR7 | UC12 — Track application status | TC011 | Must-have | Sprint 2 |
| US025 | FR9, FR11 | UC14 — View anonymized analytics | TC013 | Could-have | Sprint 3 |
| US026 | FR11, NFR15 | UC14 | TC013 | Could-have | Sprint 3 |
| US027 | NFR13 | UC1 — security layer | TC-NFR02 | Must-have | Sprint 1 |
| US028 | FR15, NFR16 | UC15 | TC016 | Must-have | Sprint 2 |
| US029 | NFR13 | UC8 — payment safety | TC-NFR03 | Must-have | Sprint 2 |
| US030 | NFR17, NFR19 | All — performance | TC-NFR01 | Must-have | Ongoing |

---

## 6. Reflection: Challenges in Agile Planning as a Solo Practitioner

The brief for this assignment contains an unusual instruction: since I am the only stakeholder, I should use the internal resistance and difficulty I encountered as the material for this reflection. That instruction turned out to be more accurate than it first appeared. The challenges in Assignment 6 were not about other people disagreeing with me — they were about the different versions of myself that came into conflict.

### The Weight of Continuity

Before I could write a single user story, I had to reconcile four documents that did not all tell exactly the same story. The uploaded `SPECIFICATION.md` (v2.0), `USE_CASE_SPECIFICATIONS.md`, `TEST_CASES.md`, and `SYSTEM_REQUIREMENTS_COMPLETE.md` describe a richer system than the original Assignment 3 scope — one where learners pay fees through a certified payment gateway (UC8), submit applications directly (UC10), and university admissions officers publish programme data inside UniMatch (UC2, UC11). These flows were not present in earlier drafts. Getting the user stories right required reading each document carefully and ensuring every story mapped to both a requirement ID and a use case ID. The traceability matrix in Section 5 is not bureaucratic overhead — it is the proof that the backlog accurately reflects the system that was specified.

### The Prioritization Paradox

The hardest single decision in this assignment was where to place US014 (fee payment) and US018 (application submission) in the MoSCoW prioritization. As a Product Owner, I instinctively wanted to make them Must-have. They are core to the platform vision. They address the anti-fraud design goal that motivated the system. They are the use cases that differentiate UniMatch from a school spreadsheet. But as a Developer, I had to be honest: implementing a certified payment gateway integration in Sprint 1 — alongside authentication, the recommendation engine, RBAC, and the security foundation — is not feasible for a solo developer in 14 days. Classifying them as Should-have was not a demotion of their importance. It was an honest acknowledgement of sequencing: you cannot pay fees before you have learner profiles, programme data, and recommendations. The Should-have classification is not permanent — it becomes the Sprint 2 goal.

A related tension arose with the expanded actor model. The Assignment 5 system has seven actors whose workflows are deeply interdependent. Almost every story had a plausible Must-have argument. The discipline that broke the impasse was separating "must eventually exist" from "must be delivered in Sprint 1." The university portal (US007) is architecturally essential, but for Sprint 1 I can seed the database with test programme data. That distinction — between long-term necessity and Sprint 1 necessity — is what MoSCoW is genuinely asking. I had to apply it with more precision than in any previous assignment.

### Estimating Alone Removes the Forcing Function

Story point estimation is meant to be a team activity. The Fibonacci sequence exists partly to encode collective uncertainty — when a team disagrees between 5 and 8, that disagreement surfaces a risk needing investigation. Estimating alone removes that forcing function entirely. The recommendation engine (US008) received 8 points not because I timed it precisely, but because when I tried to write the task breakdown (T026–T030), the list kept growing. That growth — the feeling of "there's more here than I thought" — is exactly what an 8 means in Fibonacci estimation. I used task decomposition as a proxy for team disagreement: if I could not write a clean 4–5 task breakdown, the story was an 8. If I kept discovering hidden sub-tasks, it was an 8 and at risk of becoming a 13.

### The Resistance Toward Security Stories Was Worth Examining

US027, US028, US029, and US030 feel like infrastructure rather than features. A learner does not experience TLS; they experience the *absence* of data theft. The instinct was to defer them or classify them as Should-have. But `TEST_CASES.md` already includes TC-NFR02 (TLS and RBAC verification) and TC-NFR03 (no card details stored), and those tests cannot be retroactively applied to data already stored in plaintext. Security cannot be added after the fact. Recognising that resistance — and overriding it using test cases I had already written — was the most consequential Agile decision in this assignment.

### What the Process Revealed About the System

The most valuable outcome of this assignment was not the backlog itself — it was what writing user stories revealed about gaps in prior documents. US015 (*"As a Learner, I want to be clearly informed if my payment fails or times out"*) did not come from a single requirement. It came from reading UC8-AF1 and UC8-AF2 together and realising that the system's behavior in these two failure states is genuinely different and matters enormously to the learner. A payment timeout and a payment decline require different system responses. The user story format forced me to ask: whose experience is this, and what do they actually need? That question — not the format itself — is what makes Agile planning valuable.

The resistance I felt throughout this process was not an obstacle to good planning. It was evidence that the planning process was working.

---

*End of Assignment 6 — UniMatch Agile User Stories, Backlog, and Sprint Planning*

*Requirement IDs reference `SYSTEM_REQUIREMENTS_COMPLETE.md` (FR1–FR15, NFR1–NFR20). Use case IDs reference `USE_CASE_SPECIFICATIONS.md` (UC1–UC15). Test IDs reference `TEST_CASES.md` (TC001–TC017, TC-NFR01–TC-NFR05).*