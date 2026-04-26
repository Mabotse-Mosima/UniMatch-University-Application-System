# Assignment 9: Domain Modeling and Class Diagram Development
 
**System**: UniMatch – School-Based University Application & Eligibility System  
**Author**: Christinah Mmabotse Mosima  
**Date**: 2026-04-24  
**Assignment**: 9 – Domain Modeling
**Builds on**: SPECIFICATION.md v2.0 · SYSTEM_REQUIREMENTS_COMPLETE.md (FR1–FR15) · USE_CASE_SPECIFICATIONS.md (UC1–UC15) · ARCHITECTURE.md v2.0 · ASSIGNMENT_8 (STD1–STD8, AD1–AD8)
 
---
 
 
## 1. Domain Model
 
### 1.1 Overview
 
The UniMatch domain consists of seven core entities that together model the full lifecycle of a South African matric learner's university application journey — from teacher-managed profile creation through AI-driven recommendations, guided selection, secure payment, package compilation, submission, and university decision.
 
These entities are grounded directly in the components identified in ARCHITECTURE.md §4 (C4 Level 3), the state objects in Assignment 8 (STD1–STD8), and the functional requirements in SYSTEM_REQUIREMENTS_COMPLETE.md.
 
---
 
### 1.2 Core Domain Entities
 
#### Entity 1: UserAccount
 
| Field | Detail |
|---|---|
| **Description** | Represents any authenticated system user. UniMatch has seven role types; all share this entity with role-based access control enforced at every route (FR10). |
| **Attributes** | `userId: UUID`, `email: String`, `passwordHash: String`, `role: RoleEnum`, `failedAttempts: Integer`, `lockedUntil: DateTime`, `mfaSecret: String`, `createdAt: DateTime`, `updatedAt: DateTime` |
| **Methods** | `login(email, password): JWT`, `verifyMFA(otp): Boolean`, `resetPassword(newPassword): void`, `isLocked(): Boolean`, `hasRole(role): Boolean` |
| **Relationships** | Has-many AuditLogEntry. Has-many Notification (as recipient). Specialised by: TeacherProfile, AdminProfile, LearnerAccount, ParentAccount, UniversityOfficerAccount |
| **Business rules** | Account locks after 3 consecutive failed login attempts (US001). MFA is mandatory for Admin and IT Support roles (NFR14). Suspended accounts cannot login regardless of credentials. |
 
---
 
#### Entity 2: LearnerProfile
 
| Field | Detail |
|---|---|
| **Description** | Stores a Grade 12 learner's academic data. This is the central data entity — every recommendation, application, and document links back to it. It does NOT extend UserAccount because learners do not log in via a staff-facing profile; they have a separate LearnerAccount. |
| **Attributes** | `learnerId: UUID`, `fullName: String`, `schoolIdNumber: String`, `grade: Integer`, `status: ProfileStatusEnum`, `counselorId: UUID`, `schoolId: UUID`, `createdAt: DateTime`, `updatedAt: DateTime` |
| **Methods** | `isComplete(): Boolean`, `getApsScore(): Integer`, `getSubjectMarks(): Mark[]`, `generateRecommendations(): RecommendationResult[]`, `getActiveApplications(): Application[]` |
| **Relationships** | Has-many Mark (composition — marks do not exist without a profile). Has-many Application. Has-many Document. Has-many RecommendationResult. Belongs-to School. Assigned-to UserAccount (counselor). |
| **Business rules** | `schoolIdNumber` must be unique across the system (UC3-AF1). A profile requires at minimum: fullName, schoolIdNumber, grade, and at least one subject before recommendations can be generated. Recommendations require marks for ≥6 subjects for accurate APS calculation (UC5 precondition). |
 
---
 
#### Entity 3: Mark
 
| Field | Detail |
|---|---|
| **Description** | A single subject mark for a learner. Marks are the raw input to the APS calculation. They are composed within a LearnerProfile — they have no meaning independently. |
| **Attributes** | `markId: UUID`, `learnerId: UUID`, `subjectName: String`, `score: Integer`, `examType: ExamTypeEnum`, `academicYear: Integer`, `createdAt: DateTime` |
| **Methods** | `isValid(): Boolean`, `toApsPoints(): Integer`, `getLevel(): Integer` |
| **Relationships** | Belongs-to LearnerProfile (composition). Belongs-to Subject (lookup). |
| **Business rules** | Score must be between 0 and 100 inclusive (TC004). A learner may have only one mark per subject per exam type per academic year. APS conversion follows the South African National Senior Certificate (NSC) 7-point scale. |
 
---
 
#### Entity 4: UniversityProgramme
 
| Field | Detail |
|---|---|
| **Description** | A university course published by a University Admissions Officer inside UniMatch. It is the authoritative source of programme requirements used by the recommendation engine and the learner programme browser. |
| **Attributes** | `programmeId: UUID`, `universityId: UUID`, `name: String`, `faculty: String`, `minimumAps: Integer`, `requiredSubjects: SubjectRequirement[]`, `applicationDeadline: Date`, `applicationFee: Decimal`, `requiredDocuments: String[]`, `status: ProgrammeStatusEnum`, `publishedBy: UUID`, `version: Integer`, `createdAt: DateTime`, `updatedAt: DateTime` |
| **Methods** | `isActive(): Boolean`, `isExpired(): Boolean`, `publish(): void`, `deactivate(): void`, `meetsRequirements(profile: LearnerProfile): Boolean` |
| **Relationships** | Belongs-to University. Published-by UniversityOfficerAccount. Has-many Application. Has-many RecommendationResult (as evaluated programme). |
| **Business rules** | A programme cannot be published without all mandatory fields (UC2). `applicationDeadline` must be in the future at time of publication (UC2-AF2). When a live programme is updated, the previous version is retained in version history (UC2-AF3). Only Published programmes are visible to the recommendation engine and learner browser. |
 
---
 
#### Entity 5: Application
 
| Field | Detail |
|---|---|
| **Description** | Represents one learner's application to one specific university programme. This is the most state-rich entity in the system, implementing the full lifecycle from STD1 (Assignment 8). |
| **Attributes** | `applicationId: UUID`, `learnerId: UUID`, `programmeId: UUID`, `status: ApplicationStatusEnum`, `paymentReference: String`, `feeAmount: Decimal`, `submissionTimestamp: DateTime`, `acknowledgementReference: String`, `createdAt: DateTime`, `updatedAt: DateTime` |
| **Methods** | `canSubmit(): Boolean`, `submit(): void`, `updateStatus(status, actorId): void`, `isDeadlinePassed(): Boolean`, `getStatusHistory(): StatusHistoryEntry[]`, `getDocuments(): Document[]` |
| **Relationships** | Belongs-to LearnerProfile. Belongs-to UniversityProgramme. Has-many Document (aggregation). Has-many StatusHistoryEntry (composition). Has-one PaymentTransaction. |
| **Business rules** | `canSubmit()` returns true only when: paymentReference is confirmed AND all required documents are linked AND deadline has not passed (UC10 precondition — STD1 guard condition). `paymentReference` stores the gateway reference only — no card data is ever stored (TC-NFR03, US029). Status transitions follow the strict lifecycle in STD1: e.g., Accepted cannot revert to Draft. Maximum: one application per learner per programme (no duplicates). |
 
---
 
#### Entity 6: Document
 
| Field | Detail |
|---|---|
| **Description** | A file uploaded by a teacher to support an application package. Documents are virus-scanned before storage and linked to specific applications. Implements STD5 from Assignment 8. |
| **Attributes** | `documentId: UUID`, `learnerId: UUID`, `applicationId: UUID`, `documentType: DocumentTypeEnum`, `filename: String`, `storagePath: String`, `mimeType: String`, `sizeBytes: Integer`, `uploadedBy: UUID`, `virusScanStatus: ScanStatusEnum`, `status: DocumentStatusEnum`, `uploadedAt: DateTime` |
| **Methods** | `isValid(): Boolean`, `scan(): ScanStatusEnum`, `linkToApplication(applicationId): void`, `delete(): void` |
| **Relationships** | Belongs-to LearnerProfile. Belongs-to Application (aggregation). Uploaded-by UserAccount (teacher). |
| **Business rules** | Only PDF, DOC, and DOCX file types are accepted (FR6). File size must not exceed 5 MB (US016). Virus scan must complete before the file is stored (FR6). A document with status Quarantined is never stored in the document store — the event is logged (FR15, NFR16). A document must be linked to an application before it counts toward package completeness. |
 
---
 
#### Entity 7: RecommendationResult
 
| Field | Detail |
|---|---|
| **Description** | The output of the AI eligibility engine for one learner-programme pair at a specific point in time. Implements STD8 from Assignment 8. The eligibility classification and explanation factors are stored against the learner profile so guidance sessions can reference them. |
| **Attributes** | `resultId: UUID`, `learnerId: UUID`, `programmeId: UUID`, `eligibilityCategory: EligibilityEnum`, `learnerAps: Integer`, `programmeMinimumAps: Integer`, `subjectMatches: SubjectMatchDetail[]`, `isStale: Boolean`, `generatedAt: DateTime` |
| **Methods** | `classify(): EligibilityEnum`, `getExplanation(): String`, `markStale(): void`, `isCurrentFor(profile: LearnerProfile): Boolean` |
| **Relationships** | Belongs-to LearnerProfile. Evaluates UniversityProgramme. Generated-by RecommendationService. |
| **Business rules** | EligibilityEnum values: Guaranteed, Likely, Borderline, NotEligible (FR4). `isStale` is set to true whenever the linked learner's marks are updated after generation (STD8). A stale result must be regenerated before it can be shared with the learner. Results must be generated within 3 seconds (NFR18). |
 
---
 
### 1.3 Supporting Entities
 
Beyond the seven core entities, three supporting entities are required for the system to function correctly.
 
| Entity | Purpose | Key Attributes | Key Relationship |
|---|---|---|---|
| **Notification** | Represents a single alert dispatched to a user. Implements STD7. | `notificationId`, `recipientId`, `type: NotificationTypeEnum`, `status: NotifStatusEnum`, `retryCount: Integer`, `message: String`, `createdAt` | Belongs-to UserAccount as recipient |
| **AuditLogEntry** | Immutable record of every state-changing action. Implements FR15. | `entryId`, `actorId`, `action: String`, `targetType: String`, `targetId`, `oldValue: JSON`, `newValue: JSON`, `timestamp` | Belongs-to UserAccount as actor |
| **PaymentTransaction** | Records the outcome of a single fee payment. Implements STD6. | `transactionId`, `applicationId`, `status: PaymentStatusEnum`, `paymentReference: String`, `amount: Decimal`, `initiatedAt`, `resolvedAt` | Belongs-to Application (one-to-one) |
 
---
 
### 1.4 Enumerations
 
| Enum | Values |
|---|---|
| `RoleEnum` | Teacher, SchoolAdmin, Learner, Parent, UniversityAdmissions, DoEOfficial, ITSupport |
| `ApplicationStatusEnum` | Draft, FeeOutstanding, FeePaid, PackageIncomplete, PackageReady, Submitted, UnderReview, DocsRequested, Accepted, Rejected, Waitlisted, Cancelled, DeadlineMissed |
| `EligibilityEnum` | Guaranteed, Likely, Borderline, NotEligible |
| `ProgrammeStatusEnum` | Draft, Published, UnderEdit, Expired, Deactivated, Archived |
| `DocumentStatusEnum` | Uploading, Stored, Unlinked, LinkedToApp, SubmittedWithApp, Quarantined, Rejected |
| `PaymentStatusEnum` | Initiated, AwaitingGateway, Confirmed, Declined, TimedOut, Bypassed |
| `ProfileStatusEnum` | Creating, Incomplete, Active, MarksRecorded, RecommendationsGenerated, Stale, GuidanceComplete, Inactive |
| `NotificationTypeEnum` | DeadlineReminder7Day, DeadlineReminder3Day, DeadlineReminder1Day, DeadlineOverdue, StatusChange, DocumentRequest, DecisionRecorded |
 
---
 
### 1.5 Business Rules Summary
 
| Rule | Source | Enforced by |
|---|---|---|
| Unique school ID number per learner | UC3-AF1 | LearnerProfile.schoolIdNumber unique constraint |
| APS requires ≥6 subject marks | UC5 precondition | RecommendationService.generateRecommendations() |
| No card data stored — payment reference only | TC-NFR03, NFR13 | PaymentTransaction.paymentReference only (no card fields) |
| Submission requires fee + documents + deadline | UC10 | Application.canSubmit() guard |
| Recommendations marked stale on mark update | STD8 | Mark.save() triggers RecommendationResult.markStale() |
| Documents virus-scanned before storage | FR6 | Document.scan() called before Document.store() |
| One application per learner per programme | UC7-AF3 | Application unique constraint (learnerId, programmeId) |
| MFA required for Admin and IT roles | NFR14 | UserAccount.verifyMFA() on privileged role login |
| All state changes audit-logged | FR15 | AuditLogEntry created on every status update |
| DoE analytics strip all PII | NFR15 | ReportingService.anonymise() applied for DoE role |
 
---