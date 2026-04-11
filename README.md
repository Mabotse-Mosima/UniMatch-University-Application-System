# UniMatch – School-Based University Application & Eligibility System

UniMatch is a **centralized decision-support and application coordination platform** for South African high schools. It connects **learners**, **school staff** (teachers, counselors, administrators), **parents/guardians**, **university admissions offices**, and **district / Department of Education** stakeholders so that programme information, eligibility guidance, **secure fee payment** (via an external gateway), application packages, and outcomes are managed in one place.

- Staff manage academic data, import marks, run **AI/rule-based** eligibility recommendations, conduct guidance sessions, and upload recommendation letters.
- **Learners** authenticate to select programmes, complete fee steps, review packages, **submit** applications, and **track** status (Assignment 5 vision).
- **Universities** publish requirements and record admission decisions in UniMatch’s orchestration layer.
- **District/DoE** access **anonymized** analytics only.

**Authoritative Assignment 5 artefacts:** [Use_Case_Specifications.md](Use_Case_Specifications.md), [TEST_CASES.md](TEST_CASES.md), [ASSIGNMENT5_REFLECTION.md](ASSIGNMENT5_REFLECTION.md).  
**System specification (v2.0, aligned):** [SPECIFICATION.md](SPECIFICATION.md).

---

## Project Overview

**Domain**: School administration, higher-education guidance, and multi-party application coordination (South African context).  
**Problem**: Fragmented tools, missed deadlines, unclear eligibility, fraud-prone fee handling, and weak visibility for schools and government.  
**Solution**: UniMatch coordinates applications end-to-end while delegating card processing to a **certified payment gateway** and preserving POPIA-oriented design for district reporting.

---

## Assignment Progress

### Assignment 3: System Specification & Architecture
- System specification (**updated to v2.0** for Assignment 5 alignment)
- C4 architecture (Context, Container, Component, Code) — see **ARCHITECTURE.md** §1.1 for extended actors
- Technical stack: React, Node.js/Express, PostgreSQL

### Assignment 4: Stakeholder & System Requirements
- Stakeholder analysis and System Requirements Document (SRD v2.0)
- Functional and non-functional requirements with traceability to tests

### Assignment 5: Use Cases & Tests
- UML-style use case diagram (Mermaid) and detailed specifications
- Functional and non-functional test cases (including payment security and performance)
- Reflection on requirements-to-use-case-to-test traceability

---

## Project Documents

### Assignment 3
- [System Specification – SPECIFICATION.md](SPECIFICATION.md) (v2.0)
- [Architecture – ARCHITECTURE.md](ARCHITECTURE.md) (v2.0 introduction)

### Assignment 4
- [Stakeholder Analysis – STAKEHOLDER_ANALYSIS.md](STAKEHOLDER_ANALYSIS.md)
- [System Requirements – SYSTEM_REQUIREMENTS_COMPLETE.md](SYSTEM_REQUIREMENTS_COMPLETE.md)
- [Assignment 4 Reflection – ASSIGNMENT_4_REFLECTION.md](ASSIGNMENT_4_REFLECTION.md)

### Assignment 5
- [Use Case Specifications – Use_Case_Specifications.md](Use_Case_Specifications.md)
- [Test Cases – TEST_CASES.md](TEST_CASES.md)
- [Assignment 5 Reflection – ASSIGNMENT5_REFLECTION.md](ASSIGNMENT5_REFLECTION.md)

### Supporting
- [Functional Requirements – SYSTEM_REQUIREMENTS (Functional Section).md](SYSTEM_REQUIREMENTS%20(Functional%20Section).md)
- [Non-Functional Requirements – SYSTEM_REQUIREMENTS (Non-Functional Section).md](SYSTEM_REQUIREMENTS%20(Non-Functional%20Section).md)

---

## Planned Tech Stack

- **Frontends**: React (TypeScript) — staff portal, learner portal, university admissions UI (separate apps or modules as needed)
- **Backend**: Node.js with Express (RESTful API), RBAC, audit logging
- **Database**: PostgreSQL
- **Integrations**: Payment gateway (PCI scope minimized), email/SMS providers
- **Deployment**: Cloud-hosted (HTTPS everywhere)

---

- **Frontend**: React (TypeScript), responsive web dashboard
- **Backend**: Node.js with Express (RESTful API)
- **Database**: PostgreSQL (relational)
- **Notifications**: Email-based deadline reminders (conceptual; may be mocked)
- **Deployment**: Cloud-hosted (conceptual) with HTTPS access

**Traceability:** Requirement IDs in **TEST_CASES.md** map to **SYSTEM_REQUIREMENTS_COMPLETE.md** (FR1–FR15, NFR1–NFR20). **SPECIFICATION.md** v2.0 describes the same product vision as **Use_Case_Specifications.md**. Implementation may follow **Phase 1 / Phase 2** in SPECIFICATION §1.4.

## Project Board — Assignment 7

This project uses a customised **Automated Kanban** board managed through GitHub Projects.
View the live board: [UniMatch Project Board](https://github.com/users/Mabotse-Mosima/projects/6)

### Column structure

| Column | Purpose |
|---|---|
| Backlog | All issues not yet assigned to the current sprint |
| To Do | Issues committed to the current sprint, ready to start |
| In Progress | Actively being worked on |
| Blocked | Work started but waiting on an external dependency |
| In Review | Submitted deliverables pending feedback |
| Testing | Implementation complete; acceptance criteria being verified against TEST_CASES.md |
| Done | Definition of Done satisfied; issue closed and linked to sprint milestone |

### Why Automated Kanban?
Automated Kanban was selected because it auto-moves issues when opened (→ To Do) and
closed (→ Done), eliminating manual card maintenance for a solo developer playing all
three Scrum roles.

### Custom columns added
- **Blocked**: Added to make external dependencies visible. WIP limit: 2 tasks.
- **Testing**: Added to enforce the Definition of Done — coded ≠ done until tested.
  WIP limit: 3 tasks.

### Labels
Every issue is labelled with MoSCoW priority (`must-have`, `should-have`, `could-have`),
story points (`SP:2`, `SP:3`, `SP:5`, `SP:8`), and sprint (`sprint-1`, `sprint-2`, etc.).
All Sprint 1 issues are assigned to @Mabotse-Mosima.
