# UniMatch – System Requirements Document (SRD)

**Author**: Mmabotse Mosima  
**Date**: 2026-03-20  
**Version**: 2.0  
**Assignment**: 4 - Stakeholder and System Requirements Documentation  
**Alignment**: This SRD is the **requirements baseline** for functional and non-functional IDs used in **TEST_CASES.md**. It is **consistent** with the **Assignment 5** vision in **Use_Case_Specifications.md** (learners, parents, university admissions, payment gateway orchestration, notifications). **SPECIFICATION.md** v2.0 (2026-03-29) consolidates the same target system description for Assignments 3–5.

---

## Document Overview

This System Requirements Document (SRD) provides comprehensive functional and non-functional requirements for the UniMatch system, building upon the stakeholder analysis conducted in Assignment 4. The requirements are traceable to stakeholder needs and include specific acceptance criteria and measurable quality attributes. Assignment 5 use cases and tests **realize** these requirements in verifiable scenarios.

---

## 1. Stakeholder Analysis Summary

### 1.1 Stakeholder Analysis Table

| Stakeholder                     | Role                                                   | Key Concerns                               | Pain Points                              | Success Metrics                            |
| ------------------------------- | ------------------------------------------------------ | ------------------------------------------ | ---------------------------------------- | ------------------------------------------ |
| Teacher / Counselor             | Manages learner academic data and application tracking | Easy learner monitoring, deadline tracking, accurate recommendations | Manual spreadsheets, missed applications, time-consuming eligibility calculations | 30% reduction in missed deadlines, 50% faster recommendation generation |
| School Administrator            | Oversees school performance and reporting              | Accurate reports and oversight, compliance tracking, resource management | No centralized learner tracking system, manual report compilation | Reports generated in < 1 minute, 100% compliance documentation |
| Department of Education         | Monitors education outcomes across schools             | Reliable aggregated statistics, policy compliance, resource allocation | Lack of data visibility across schools, delayed reporting cycles | Accurate national placement statistics, quarterly reporting compliance |
| Learners (Indirect Stakeholder) | Benefit from guidance decisions                        | Fair university recommendations, timely application support | Poor career guidance, missed opportunities, unclear eligibility | Increased university acceptance rate, 90% satisfaction with guidance |
| School IT Support               | Maintains technical infrastructure                     | System stability, easy maintenance, security compliance | Difficult system deployments, lack of technical documentation | ≤1 hour maintenance downtime monthly, 99.9% uptime |
| University Admissions Offices   | Receive better-prepared applicants                     | Accurate supporting documentation, qualified candidates | Incomplete or incorrect applications, verification delays | Reduced incomplete applications by 40%, faster processing times |
| System Developers               | Maintain and enhance system                            | Modular and maintainable architecture, rapid deployment | Hard-to-update legacy systems, technical debt | New features deployed within sprint cycles, 95% code coverage |
| Parents/Guardians               | Support children's university applications             | Transparency in application process, timely updates | Lack of visibility into application status, communication gaps | 80% parent satisfaction, reduced inquiry calls to school |

---

## 2. Functional Requirements

### 2.1 Learner Management Requirements

| ID   | Requirement                                                                                     | Acceptance Criteria                                             | Stakeholder(s) Addressed |
| ---- | ----------------------------------------------------------------------------------------------- | --------------------------------------------------------------- | ------------------------ |
| FR1  | The system shall allow teachers to create and manage learner profiles.                          | Teacher can add/edit learner data successfully with validation. | Teachers, Administrators |
| FR2  | The system shall allow importing learner marks via CSV upload.                                  | Uploaded file validates format before saving with error reporting. | Teachers, IT Support |
| FR14 | The system shall support bulk operations for learner data management.                          | Teachers can perform bulk updates on multiple learners simultaneously. | Teachers |

### 2.2 Application and Recommendation Requirements

| ID   | Requirement                                                                                     | Acceptance Criteria                                             | Stakeholder(s) Addressed |
| ---- | ----------------------------------------------------------------------------------------------- | --------------------------------------------------------------- | ------------------------ |
| FR3  | The system shall generate university eligibility recommendations automatically.                 | Recommendations appear within 3 seconds after marks submission. | Teachers, Learners |
| FR4  | The system shall categorize recommendations as Guaranteed, Likely, Borderline, or Not Eligible. | Categories match predefined APS rules with accuracy > 95%. | Teachers, University Admissions |
| FR5  | The system shall allow staff to update application status.                                      | Status changes saved and visible immediately with audit trail. | Teachers, Administrators |
| FR6  | The system shall allow uploading recommendation letters.                                        | Only PDF/DOCX accepted; files stored securely with virus scanning. | Teachers, University Admissions |

### 2.3 Reporting and Analytics Requirements

| ID   | Requirement                                                                                     | Acceptance Criteria                                             | Stakeholder(s) Addressed |
| ---- | ----------------------------------------------------------------------------------------------- | --------------------------------------------------------------- | ------------------------ |
| FR7  | The system shall display a dashboard showing learner application progress.                      | Dashboard loads in < 2 seconds with real-time statistics. | All Stakeholders |
| FR9  | The system shall allow administrators to generate downloadable reports.                         | Reports export as PDF or CSV with customizable date ranges. | Administrators, Department of Education |
| FR11 | The system shall allow Department of Education users to view anonymized analytics.              | Personal learner data is hidden; only aggregated statistics shown. | Department of Education |

### 2.4 Communication and Notification Requirements

| ID   | Requirement                                                                                     | Acceptance Criteria                                             | Stakeholder(s) Addressed |
| ---- | ----------------------------------------------------------------------------------------------- | --------------------------------------------------------------- | ------------------------ |
| FR8  | The system shall send deadline reminder notifications.                                          | Automated reminders sent 3 days before deadline via email and SMS. | Teachers, Parents, Learners |
| FR12 | The system shall enable parent/guardian access to view application status.                     | Parents can view their child's progress with secure authentication. | Parents/Guardians |
| FR13 | The system shall provide application deadline management and tracking.                          | System tracks all deadlines and sends escalating reminders. | Teachers, Administrators |

### 2.5 System Administration and Security Requirements

| ID   | Requirement                                                                                     | Acceptance Criteria                                             | Stakeholder(s) Addressed |
| ---- | ----------------------------------------------------------------------------------------------- | --------------------------------------------------------------- | ------------------------ |
| FR10 | The system shall provide role-based access control.                                             | Users only access permitted features based on their assigned role. | All Stakeholders, IT Support |
| FR15 | The system shall maintain an audit log of all system activities.                               | All user actions logged with timestamps and user identification. | Administrators, IT Support, Developers |

---

## 3. Non-Functional Requirements

### 3.1 Usability Requirements

| ID   | Requirement                                                                                     | Measurable Criteria                                              | Stakeholder(s) Addressed |
| ---- | ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- | ------------------------ |
| NFR1 | Accessibility Compliance                                                                        | WCAG 2.1 AA compliance verified by automated testing tools       | All Users, Teachers |
| NFR2 | Task Efficiency                                                                                | Common tasks completed in ≤3 clicks from dashboard               | Teachers, Administrators |
| NFR3 | Training Time                                                                                  | New users trained in ≤2 hours for core functions                 | All Stakeholders |

### 3.2 Deployability Requirements

| ID   | Requirement                                                                                     | Measurable Criteria                                              | Stakeholder(s) Addressed |
| ---- | ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- | ------------------------ |
| NFR4 | Platform Deployment                                                                            | System deployed in <30 minutes using Docker containers           | IT Support, Developers |
| NFR5 | Environment Management                                                                         | Automated CI/CD pipeline for dev/test/prod environments          | Developers, IT Support |
| NFR6 | Backup and Recovery                                                                            | Daily automated backups; RTO ≤4 hours, RPO ≤24 hours            | IT Support, Administrators |

### 3.3 Maintainability Requirements

| ID   | Requirement                                                                                     | Measurable Criteria                                              | Stakeholder(s) Addressed |
| ---- | ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- | ------------------------ |
| NFR7 | Modular Architecture                                                                            | Independent module deployment without system restart              | Developers, IT Support |
| NFR8 | Documentation Coverage                                                                          | 90% code coverage for critical modules with comprehensive docs    | Developers |
| NFR9 | Update Frequency                                                                                | Security patches within 7 days; monthly updates with ≤15 min downtime | IT Support, Developers |

### 3.4 Scalability Requirements

| ID   | Requirement                                                                                     | Measurable Criteria                                              | Stakeholder(s) Addressed |
| ---- | ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- | ------------------------ |
| NFR10| User Capacity                                                                                  | Support 1,000 learners/school; 10,000 concurrent users total     | Administrators, IT Support |
| NFR11| Multi-School Expansion                                                                         | Support 100+ schools within 2 years without redesign             | Department of Education, Administrators |
| NFR12| Data Growth Handling                                                                            | Handle 50GB new data annually with <10% performance impact       | IT Support, Developers |

### 3.5 Security Requirements

| ID   | Requirement                                                                                     | Measurable Criteria                                              | Stakeholder(s) Addressed |
| ---- | ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- | ------------------------ |
| NFR13| Data Encryption                                                                                 | TLS 1.3 for transit; AES-256 for rest                            | All Stakeholders |
| NFR14| Access Control                                                                                  | RBAC with MFA for admin accounts                                 | IT Support, Administrators |
| NFR15| Data Privacy Compliance                                                                         | POPIA compliance with automated retention policies               | Administrators, Department of Education |
| NFR16| Security Auditing                                                                               | Real-time monitoring and alerting for security events            | IT Support, Developers |

### 3.6 Performance Requirements

| ID   | Requirement                                                                                     | Measurable Criteria                                              | Stakeholder(s) Addressed |
| ---- | ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- | ------------------------ |
| NFR17| Response Time                                                                                   | Dashboard loads ≤2 seconds normal, ≤4 seconds peak load          | All Users |
| NFR18| Recommendation Processing                                                                       | Recommendations generated ≤3 seconds after marks submission      | Teachers, Learners |
| NFR19| Concurrent User Support                                                                         | 500 concurrent users with <5% response time degradation          | All Stakeholders |
| NFR20| Data Processing Performance                                                                     | 1,000 record CSV import completed ≤60 seconds                    | Teachers, IT Support |

---

## 4. Requirements Traceability Matrix

### 4.1 Stakeholder to Requirement Mapping

| Stakeholder | Functional Requirements | Non-Functional Requirements |
|-------------|------------------------|----------------------------|
| Teacher/Counselor | FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR8, FR13, FR14 | NFR1, NFR2, NFR3, NFR17, NFR18, NFR20 |
| School Administrator | FR1, FR5, FR7, FR9, FR10, FR13, FR15 | NFR2, NFR6, NFR10, NFR14, NFR17 |
| Department of Education | FR11, FR9 | NFR11, NFR15 |
| Learners | FR3, FR4, FR8, FR12, FR13 | NFR1, NFR18 |
| School IT Support | FR10, FR15 | NFR4, NFR5, NFR6, NFR7, NFR9, NFR10, NFR12, NFR14, NFR16 |
| University Admissions | FR4, FR6 | NFR13, NFR18 |
| System Developers | FR15 | NFR7, NFR8, NFR9 |
| Parents/Guardians | FR8, FR12 | NFR1, NFR3 |

---

## 5. Priority Classification

### 5.1 Requirements Priority Matrix

| Priority | Functional Requirements | Non-Functional Requirements |
|----------|------------------------|----------------------------|
| **High** | FR1, FR2, FR3, FR5, FR10 | NFR1, NFR13, NFR14, NFR17 |
| **Medium** | FR4, FR6, FR7, FR8, FR9, FR11, FR13 | NFR2, NFR4, NFR5, NFR6, NFR10, NFR18, NFR19 |
| **Low** | FR12, FR14, FR15 | NFR3, NFR7, NFR8, NFR9, NFR11, NFR12, NFR15, NFR16, NFR20 |

---

## 6. Assumptions and Constraints

### 6.1 Assumptions

1. Schools have reliable internet connectivity for cloud-based system access
2. Teachers have basic computer literacy and can receive minimal training
3. Department of Education will provide standardized university programme requirements
4. Parents have access to email or mobile devices for notifications
5. Schools have existing IT infrastructure that can support the system requirements

### 6.2 Constraints

1. System must comply with South African POPIA data protection regulations
2. Limited budget for initial deployment and ongoing maintenance
3. Must integrate with existing school administrative systems where possible
4. Deployment timeline limited to academic year calendar
5. System must be accessible across various device types and screen sizes

---

## 7. Success Criteria

The UniMatch system will be considered successful when:

1. **Stakeholder Satisfaction**: 80% of stakeholders report satisfaction with system functionality
2. **Performance Targets**: All performance requirements (NFR17-20) are met consistently
3. **Adoption Rate**: 90% of target schools actively using the system within 6 months
4. **Data Quality**: 95% accuracy in recommendation calculations and application tracking
5. **System Reliability**: 99.9% uptime achieved with rapid issue resolution
6. **Compliance**: Full compliance with POPIA and other regulatory requirements
7. **Cost Efficiency**: 30% reduction in manual administrative processes

---

## 8. Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-01 | Mmabotse Mosima | Initial functional requirements (Assignment 3) |
| 2.0 | 2026-03-20 | Mmabotse Mosima | Complete stakeholder analysis and enhanced requirements (Assignment 4) |

---

*This document serves as the authoritative source for UniMatch system requirements and will be updated as stakeholder needs evolve throughout the development lifecycle.*
