# SPECIFICATION – UniMatch: School-Based University Application & Eligibility System

Author: Mmabotse Mosima  
Date: 2025-12-01  
Version: 1.0

---

## 1. Introduction

### 1.1 Project Title

**UniMatch – School-Based University Application & Eligibility System**

### 1.2 Domain

**Domain**: School administration and higher-education guidance, focused on South African high schools.

**Updated vision (Assignment 5):** UniMatch is a **centralized decision-support and application coordination platform** that connects **learners**, **school staff** (teachers, counselors, administrators), **parents/guardians**, **university admissions offices**, and **government/district** stakeholders. It provides verified programme information, guided eligibility recommendations, **secure fee payment** (via an external payment gateway—UniMatch does not store card data), application package compilation, submission orchestration, and notifications—while **school staff remain responsible** for academic data quality, guidance sessions, and recommendation letters.

The detailed use case model, lifecycle states, and actor relationships are defined in **[Use_Case_Specifications.md](Use_Case_Specifications.md)**.

### 1.3 Problem Statement

Many South African high schools still rely on manual or fragmented methods (paper files, individual spreadsheets, ad-hoc notes) to:

- Track whether each learner has applied to university.
- Check eligibility against multiple university programmes.
- Ensure supporting documents (recommendation letters, essays, etc.) are submitted.
- Report outcomes to school management and government.

This leads to:

- Late or incomplete applications and missed programme deadlines.
- Learners applying to programmes where they are not competitive.
- Limited visibility for school leadership and government on placement trends.
- Heavy manual work for teachers and inconsistent communication with parents.

**UniMatch** addresses this by providing **one coordinated platform** where:

- **Staff** manage learner profiles, import marks, run eligibility recommendations, conduct guidance, compile packages, and upload recommendation documents.
- **Learners** authenticate to select programmes, pay official fees through a **certified external gateway**, submit applications, and track status.
- **Parents/guardians** can monitor progress and receive notifications (per role rules).
- **University admissions** publish programme requirements and record decisions **inside UniMatch** (orchestration layer—not a replacement for each university’s full admission system).
- **District/DoE** access **anonymized** analytics only.

### 1.4 Scope, Phasing, and Feasibility

This remains an **individual semester project**; implementation may be **phased** while the **specification** describes the full target system consistent with Assignment 5.

**In Scope for Implementation (MVP):**

- Multi-role authentication and RBAC (Learner, Teacher/Counselor, Parent/Guardian, School Administrator, University Admissions, District/DoE read-only, School IT Support).
- Learner-facing flows: programme exploration, selection, fee payment confirmation, package review, submission, status tracking, notifications.
- Staff flows: learner and marks management, CSV import, AI/rule-based recommendations with explanatory factors, guidance session notes, document uploads, application status updates.
- University admissions flows: publish/maintain programmes, review submissions, record decisions (audit trail).
- Integrations: external **payment gateway** (cards not stored in UniMatch), email/SMS for notifications, optional future hooks to university systems.

**Phasing (feasibility for one developer):**

- **Phase 1 (core):** Staff dashboard, learner profiles, marks, recommendations, documents, basic application tracking, audit logging.
- **Phase 2:** Learner and parent portals, payment integration, university admissions workflows, full notification suite, performance hardening per NFRs.

**Out of scope / deferred (unless course expands scope):**

- NSFAS or full national funding integration (may be future enhancement).
- Full legal POPIA certification (design follows POPIA principles; formal certification out of scope).
- Replacing every university’s entire backend admission system—UniMatch **coordinates** and **records** outcomes as per use cases.

Version 1.0 of this document described a **staff-only** MVP; **Version 2.0** supersedes that boundary for stakeholder and academic alignment with **[Use_Case_Specifications.md](Use_Case_Specifications.md)**, **[TEST_CASES.md](TEST_CASES.md)**, and **[ASSIGNMENT5_REFLECTION.md](ASSIGNMENT5_REFLECTION.md)**.

---

## 2. System Overview

UniMatch is a **web-based coordination platform** that supports the **end-to-end** matric university application journey described in Assignment 5:

- **Learner & school data**: Profiles, subjects, marks, counselor assignment; bulk CSV import where applicable.
- **Eligibility & guidance**: Rule-based / AI-assisted recommendations (Guaranteed / Likely / Borderline / Not Eligible) with transparent factors; structured guidance sessions documented by staff.
- **Programme catalogue**: University admissions maintain published programme requirements, fees, and deadlines.
- **Applications**: Lifecycle from Draft through fee payment, package readiness, submission, university review, and final decision (see lifecycle in **Use_Case_Specifications.md** §4).
- **Payments**: Application fees processed via **external payment gateway**; UniMatch stores only references and status—not card numbers.
- **Documents**: Recommendation letters and supporting files uploaded by staff; learners review packages before submission per use cases.
- **Dashboards & reporting**: School dashboards; **anonymized** district/DoE analytics; exportable reports.
- **Notifications**: Email/SMS/in-app reminders for deadlines, decisions, and missing documents—role-appropriate.

Client applications include **staff web UI**, **learner web/app experience**, and **parent/guardian** visibility where requirements permit—all against a shared **REST API** and relational datastore as shown in **ARCHITECTURE.md**.

---

## 3. Functional Requirements

### 3.1 Learner Management

- **FR-1**: The system shall allow authorized staff to create learner profiles with:
  - Full name
  - ID or school number
  - Grade (e.g., 12)
  - Assigned counselor/teacher

- **FR-2**: The system shall allow staff to record and update learner subjects and marks (e.g., percentages or levels).

- **FR-3**: The system shall allow import of learner marks from a CSV file with a defined template.

- **FR-4**: The system shall allow searching and filtering learners by name, grade, counselor, and application status.

### 3.2 Application Tracking

- **FR-5**: The system shall allow staff to create university application records per learner, including:
  - Target university and programme.
  - Application date.
  - Application channel (optional, e.g., online, manual).

- **FR-6**: The system shall support the following application statuses:
  - `Not Applied`
  - `Applied`
  - `Pending`
  - `Accepted`
  - `Rejected`
  - `Missing Documents`

- **FR-7**: The system shall allow staff to update application status and record notes (e.g., reasons for rejection, follow-up actions).

- **FR-8**: The system shall display a per-learner timeline/history of application status changes.

### 3.3 University and Programme Management

- **FR-9**: The system shall allow staff (typically administrators) to manage a catalogue of universities and programmes.

- **FR-10**: For each programme, the system shall store:
  - Programme name and code.
  - University name and faculty.
  - Minimum APS (or similar score).
  - Required or preferred subjects and minimum levels.

- **FR-11**: The system shall allow staff to update programme requirements annually.

### 3.4 Recommendation Engine

- **FR-12**: The system shall compute an APS-like score for each learner based on configured rules (e.g., sum of top 6 subjects, or similar).

- **FR-13**: The system shall compare learner marks and APS score to each programme’s minimum requirements.

- **FR-14**: The system shall assign an eligibility category for each learner-programme pair:
  - `Guaranteed` – Meets/Exceeds requirements comfortably.
  - `Likely` – Meets minimum requirements.
  - `Borderline` – Slightly below recommended thresholds.
  - `Not Eligible` – Does not meet minimum requirements.

- **FR-15**: The system shall generate a ranked list of recommended programmes per learner and display it on the learner’s profile.

- **FR-16**: Staff shall be able to filter recommendations by university, faculty, or eligibility category.

### 3.5 Document Upload and Management

- **FR-17**: The system shall allow staff to upload recommendation letters and supporting documents for each learner.

- **FR-18**: The system shall support at least the following file types:
  - PDF (`.pdf`)
  - Word documents (`.doc`, `.docx`)

- **FR-19**: The system shall allow multiple documents per learner and store metadata:
  - Document type (e.g., recommendation letter, motivational letter).
  - Uploader (staff user).
  - Upload date.

- **FR-20**: Only authenticated staff with appropriate permissions shall be able to view or download learner documents.

### 3.6 Dashboards and Reporting

- **FR-21**: The system shall provide a dashboard with key metrics, such as:
  - Number of learners by application status.
  - Number of accepted offers.
  - Distribution of applications by university.

- **FR-22**: The system shall present these metrics using simple charts (e.g., bar or pie charts) and tables.

- **FR-23**: School administrators shall be able to export reports to CSV, including:
  - Learner-level application summaries.
  - Aggregated statistics for school or grade.

- **FR-24**: The system shall support generating anonymized, aggregated reports suitable for government/district officials (no personally identifiable learner data).

### 3.7 Notifications and Alerts

- **FR-25**: The system shall allow configuration of important application deadlines (e.g., university closing dates).

- **FR-26**: The system shall flag learners with missing documents or incomplete application information.

- **FR-27**: The system shall notify staff (e.g., via an in-app alert list) when:
  - A deadline is approaching for a learner who has not applied.
  - A learner has status `Missing Documents`.

- **FR-28**: The system may (optionally) send email reminders to staff, but this can be mocked or simplified in implementation.

### 3.8 User Management and Security

- **FR-29**: The system shall support user accounts with at least the following roles:
  - Teacher/Counselor
  - School Administrator
  - Government/District Official (read-only, aggregated data)

- **FR-30**: The system shall restrict functionality based on role:
  - Teachers/Counselors: Manage assigned learners, applications, documents, and view recommendations.
  - Administrators: Full access to all learners, configuration, and reports.
  - Government/District: Read-only access to anonymized, aggregated statistics.

- **FR-31**: The system shall require authentication (username/email and password) for all access.

---

## 4. Non-Functional Requirements

### 4.1 Usability

- **NFR-1**: The UI shall be intuitive, with minimal clicks required to perform common tasks (view learner list, update status, add marks).
- **NFR-2**: The dashboard shall present clear visual indicators (colors, icons) for application statuses.
- **NFR-3**: The system shall be responsive and usable on laptops and tablets.

### 4.2 Performance

- **NFR-4**: The system shall support at least 500–1000 learner records per school with acceptable response time (typically \< 2 seconds for standard queries).
- **NFR-5**: Batch operations like CSV import/export should complete within a reasonable time (e.g., \< 30 seconds for typical school data sizes).

### 4.3 Reliability and Availability

- **NFR-6**: Target conceptual availability of 99% (design goal).
- **NFR-7**: The system shall handle unexpected failures gracefully, returning meaningful error messages instead of crashing.

### 4.4 Security and Privacy

- **NFR-8**: All access to the system shall be authenticated.
- **NFR-9**: Role-based authorization shall prevent users from accessing data they are not allowed to see.
- **NFR-10**: Sensitive data (e.g., passwords) shall be stored securely (e.g., hashed, never in plain text).
- **NFR-11**: The system shall follow POPIA principles conceptually (minimal data, restricted access, audit logs), though full legal certification is out of scope.

### 4.5 Maintainability

- **NFR-12**: The system shall be built using a modular architecture with clear separation between frontend, backend, and database.
- **NFR-13**: Programme requirements should be configurable from data (database) rather than hard-coded to ease annual updates.

### 4.6 Accessibility

- **NFR-14**: The UI should follow basic WCAG 2.1 guidelines, such as:
  - High-contrast color schemes.
  - Clear font sizes.
  - Support for keyboard navigation.

---

## 5. System Actors and Roles

| Actor                     | Description                                                                                 |
|---------------------------|---------------------------------------------------------------------------------------------|
| Teacher / Counselor       | Manages learner data, enters marks, tracks applications, uploads recommendation letters.   |
| School Administrator      | Manages users, oversees all learners, configures programmes, generates reports.            |
| Government / District     | Reads anonymized, aggregated statistics only (no direct learner-level data).              |
| System (UniMatch)         | Executes recommendation logic, stores data, sends notifications, and logs user actions.    |

---

## 6. Use Cases (High-Level)

1. **UC-1: Add Learner Marks**
   - Actor: Teacher/Counselor
   - Goal: Record or import subject marks for a learner.
   - Outcome: Learner’s profile is updated and ready for eligibility calculations.

2. **UC-2: Generate University Recommendations**
   - Actor: Teacher/Counselor
   - Goal: View a ranked list of suitable programmes for a learner.
   - Outcome: System shows programmes categorized as Guaranteed/Likely/Borderline/Not Eligible.

3. **UC-3: Upload Recommendation Letter**
   - Actor: Counselor/Teacher
   - Goal: Attach a recommendation letter or supporting document to a learner’s profile.
   - Outcome: Document metadata and file are stored securely and visible to staff.

4. **UC-4: Track Application Status**
   - Actor: Teacher/Counselor
   - Goal: Update and monitor a learner’s application status across different universities.
   - Outcome: Application statuses and notes are up to date and visible on dashboards.

5. **UC-5: Generate School Report**
   - Actor: School Administrator
   - Goal: Export a report for school or government submission.
   - Outcome: CSV (and optionally PDF) report is generated with relevant statistics.

6. **UC-6: View Dashboard Overview**
   - Actor: Any staff role (with appropriate permissions)
   - Goal: Quickly see a summary of learner progress and application statuses.
   - Outcome: Dashboard view with charts and tables.

---

## 7. Data Requirements / Conceptual Database Model

**Key conceptual tables/entities:**

- **Learners**
  - `id`, `full_name`, `school_id`, `grade`, `id_number`, `counselor_id`
- **Subjects**
  - `id`, `name`, `code`
- **Marks**
  - `id`, `learner_id`, `subject_id`, `score`, `exam_type` (e.g., final/term), `year`
- **Universities**
  - `id`, `name`, `province`
- **Programmes**
  - `id`, `university_id`, `name`, `faculty`, `min_aps`, `subject_requirements` (JSON/structured)
- **Applications**
  - `id`, `learner_id`, `programme_id`, `status`, `applied_date`, `notes`
- **Documents**
  - `id`, `learner_id`, `file_name`, `file_type`, `file_path`, `document_type`, `uploaded_by`, `uploaded_at`
- **Users**
  - `id`, `name`, `email`, `role` (Learner, Staff, Parent, Admin, University, District, IT), `password_hash`, `created_at`
- **Payments** *(Assignment 5)*  
  - `id`, `application_id`, `gateway_reference`, `amount`, `status`, `timestamp` — **no** card or CVV storage
- **Notifications** *(Assignment 5)*  
  - `id`, `user_id`, `channel`, `payload`, `read_at`

---

## 8. Assumptions, Risks & Constraints

### 8.1 Assumptions

- Schools can provide accurate and up-to-date learner marks.
- Programme requirements can be manually maintained annually.
- Internet access is available for staff at least during working hours.

### 8.2 Risks

- Out-of-date university requirements may lead to incorrect recommendations.
- Human error in data entry can affect eligibility results.
- Connectivity problems in some rural schools can reduce system availability.

### 8.3 Constraints

- Single developer (individual project) with limited time.
- Limited access to official university APIs for integration.
- POPIA legal compliance can only be demonstrated conceptually, not formally.

---

## 9. Future Enhancements

Items **below** extend the Assignment 5 baseline rather than replace it:

- Deeper **real-time** bidirectional sync with each university’s legacy admission system (beyond orchestration and decision recording in UniMatch).
- **Advanced** ML-based recommendation models (beyond rule-based + explanatory factors in current spec).
- **NSFAS** or other funding status integration.
- **Native mobile apps** for learners and parents (optional; responsive web remains baseline).
- **Multi-tenant** SaaS operation at national scale (architecture supports growth; operations model TBD).