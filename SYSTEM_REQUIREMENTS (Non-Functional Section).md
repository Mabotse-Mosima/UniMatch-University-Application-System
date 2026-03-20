## 2. Non-Functional Requirements

Non-functional requirements define the quality attributes and operational constraints of the UniMatch system.

---

### 2.1 Usability

**NFR1 – Accessibility**
The system interface shall comply with WCAG 2.1 accessibility standards to support users with visual or physical impairments, including keyboard navigation and screen reader compatibility.

**NFR2 – Ease of Use**
Teachers shall be able to complete common tasks (adding learner data or updating application status) within a maximum of 3 clicks from the dashboard.

**NFR3 – Training Time**
New users shall require no more than 2 hours of training to perform core system functions independently.

---

### 2.2 Deployability

**NFR4 – Platform Deployment**
The system shall be deployable on Linux-based cloud servers using containerized deployment (e.g., Docker) with setup time < 30 minutes.

**NFR5 – Environment Configuration**
The system shall support separate development, testing, and production environments with automated deployment pipelines.

**NFR6 – Backup and Recovery**
System shall support automated daily backups with recovery time objective (RTO) of 4 hours and recovery point objective (RPO) of 24 hours.

---

### 2.3 Maintainability

**NFR7 – Modular Architecture**
The system shall follow a modular service-based architecture allowing independent updates without affecting other components.

**NFR8 – Documentation**
All APIs and system components shall include technical documentation to support future maintenance and integration, with 90% code coverage for critical modules.

**NFR9 – Update Frequency**
Security patches shall be applied within 7 days of release; feature updates shall be deployed monthly without system downtime > 15 minutes.

---

### 2.4 Scalability

**NFR10 – User Capacity**
The system shall support at least 1,000 learners per school without performance degradation and handle 10,000 concurrent users across multiple schools.

**NFR11 – Multi-School Expansion**
The architecture shall allow onboarding of additional schools without requiring major system redesign, supporting 100+ schools within 2 years.

**NFR12 – Data Growth**
System shall handle 50GB of new data annually with < 10% performance impact over 5 years.

---

### 2.5 Security

**NFR13 – Data Encryption**
All sensitive learner data shall be encrypted in transit using TLS 1.3 and encrypted at rest within the database using AES-256 encryption.

**NFR14 – Access Control**
The system shall implement role-based access control ensuring users can only access features permitted by their role with multi-factor authentication for admin accounts.

**NFR15 – Data Privacy**
System shall comply with POPIA (Protection of Personal Information Act) requirements for South African data protection with automated data retention policies.

**NFR16 – Security Auditing**
All security events shall be logged and monitored with real-time alerting for suspicious activities.

---

### 2.6 Performance

**NFR17 – Response Time**
Dashboard pages shall load within 2 seconds under normal operating conditions and 4 seconds during peak load.

**NFR18 – Recommendation Processing**
University eligibility recommendations shall be generated within 3 seconds after learner marks are submitted.

**NFR19 – Concurrent Users**
System shall support 500 concurrent users with < 5% degradation in response time.

**NFR20 – Data Processing**
Bulk CSV imports of up to 1,000 learner records shall complete within 60 seconds.

---
