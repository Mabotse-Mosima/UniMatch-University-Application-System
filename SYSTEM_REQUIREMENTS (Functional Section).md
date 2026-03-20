# UniMatch – System Requirements Document (SRD)

## 1. Functional Requirements

### 1.1 Learner Management Requirements

| ID   | Requirement                                                                                     | Acceptance Criteria                                             | Stakeholder(s) Addressed |
| ---- | ----------------------------------------------------------------------------------------------- | --------------------------------------------------------------- | ------------------------ |
| FR1  | The system shall allow teachers to create and manage learner profiles.                          | Teacher can add/edit learner data successfully with validation. | Teachers, Administrators |
| FR2  | The system shall allow importing learner marks via CSV upload.                                  | Uploaded file validates format before saving with error reporting. | Teachers, IT Support |
| FR14 | The system shall support bulk operations for learner data management.                          | Teachers can perform bulk updates on multiple learners simultaneously. | Teachers |

### 1.2 Application and Recommendation Requirements

| ID   | Requirement                                                                                     | Acceptance Criteria                                             | Stakeholder(s) Addressed |
| ---- | ----------------------------------------------------------------------------------------------- | --------------------------------------------------------------- | ------------------------ |
| FR3  | The system shall generate university eligibility recommendations automatically.                 | Recommendations appear within 3 seconds after marks submission. | Teachers, Learners |
| FR4  | The system shall categorize recommendations as Guaranteed, Likely, Borderline, or Not Eligible. | Categories match predefined APS rules with accuracy > 95%. | Teachers, University Admissions |
| FR5  | The system shall allow staff to update application status.                                      | Status changes saved and visible immediately with audit trail. | Teachers, Administrators |
| FR6  | The system shall allow uploading recommendation letters.                                        | Only PDF/DOCX accepted; files stored securely with virus scanning. | Teachers, University Admissions |

### 1.3 Reporting and Analytics Requirements

| ID   | Requirement                                                                                     | Acceptance Criteria                                             | Stakeholder(s) Addressed |
| ---- | ----------------------------------------------------------------------------------------------- | --------------------------------------------------------------- | ------------------------ |
| FR7  | The system shall display a dashboard showing learner application progress.                      | Dashboard loads in < 2 seconds with real-time statistics. | All Stakeholders |
| FR9  | The system shall allow administrators to generate downloadable reports.                         | Reports export as PDF or CSV with customizable date ranges. | Administrators, Department of Education |
| FR11 | The system shall allow Department of Education users to view anonymized analytics.              | Personal learner data is hidden; only aggregated statistics shown. | Department of Education |

### 1.4 Communication and Notification Requirements

| ID   | Requirement                                                                                     | Acceptance Criteria                                             | Stakeholder(s) Addressed |
| ---- | ----------------------------------------------------------------------------------------------- | --------------------------------------------------------------- | ------------------------ |
| FR8  | The system shall send deadline reminder notifications.                                          | Automated reminders sent 3 days before deadline via email and SMS. | Teachers, Parents, Learners |
| FR12 | The system shall enable parent/guardian access to view application status.                     | Parents can view their child's progress with secure authentication. | Parents/Guardians |
| FR13 | The system shall provide application deadline management and tracking.                          | System tracks all deadlines and sends escalating reminders. | Teachers, Administrators |

### 1.5 System Administration and Security Requirements

| ID   | Requirement                                                                                     | Acceptance Criteria                                             | Stakeholder(s) Addressed |
| ---- | ----------------------------------------------------------------------------------------------- | --------------------------------------------------------------- | ------------------------ |
| FR10 | The system shall provide role-based access control.                                             | Users only access permitted features based on their assigned role. | All Stakeholders, IT Support |
| FR15 | The system shall maintain an audit log of all system activities.                               | All user actions logged with timestamps and user identification. | Administrators, IT Support, Developers |

---