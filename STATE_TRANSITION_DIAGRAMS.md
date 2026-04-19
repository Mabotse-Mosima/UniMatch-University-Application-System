# Assignment 8: Object State Modeling — State Transition Diagrams
# UniMatch – School-Based University Application & Eligibility System

**Author**: Christinah Mmabotse Mosima
**Date**: 2026-04-15
**Assignment**: 8 – Object State Modeling and Activity Workflow Modeling
**Builds on**: Assignment 4 (FR1–FR15), Assignment 5 (UC1–UC15), Assignment 6 (US001–US030)

---

## Overview

This document defines state transition diagrams for 8 critical objects in UniMatch. Each diagram models the complete lifecycle of an object — every state it can occupy, every event that triggers a transition, and every guard condition that constrains movement between states. All diagrams are grounded in the functional requirements from Assignment 4 and the use case specifications from Assignment 5.

---


---
 
## 1. State Transition Diagrams
 
---
 
### STD1 — University Application
 
The Application object is the central lifecycle entity in UniMatch. It tracks a single learner's application to one university programme from first selection through to a final admission decision.
 
```mermaid
stateDiagram-v2
    [*] --> Draft : Learner adds programme to list (UC7)
 
    Draft --> FeeOutstanding : System assigns fee from programme data
    Draft --> Cancelled : Learner removes programme before payment
    Draft --> DeadlineMissed : Application deadline passes [status=Draft]
 
    FeeOutstanding --> FeePaid : Gateway returns success callback (UC8)\n[payment reference stored, no card data]
    FeeOutstanding --> Cancelled : Learner withdraws before payment
    FeeOutstanding --> DeadlineMissed : Deadline passes [status=FeeOutstanding]
 
    FeePaid --> PackageIncomplete : Teacher begins uploading documents (UC9)\n[one or more required documents missing]
    FeePaid --> PackageReady : Teacher uploads all required documents\n[all required document types present]
 
    PackageIncomplete --> PackageReady : Teacher uploads missing documents\n[all required documents now present]
 
    PackageReady --> Submitted : Learner confirms submission (UC10)\n[fee confirmed AND package complete AND deadline not passed]
    PackageReady --> DeadlineMissed : Deadline passes [status=PackageReady]
 
    Submitted --> UnderReview : University admissions officer opens application (UC11)
 
    UnderReview --> DocsRequested : Officer requests further documents
    UnderReview --> Accepted : Officer records Accept decision
    UnderReview --> Rejected : Officer records Reject decision
    UnderReview --> Waitlisted : Officer records Waitlist decision
 
    DocsRequested --> PackageIncomplete : Teacher uploads requested documents
 
    Waitlisted --> Accepted : University offers place from waitlist
    Waitlisted --> Rejected : Waitlist closes without offer
 
    Accepted --> [*]
    Rejected --> [*]
    Cancelled --> [*]
    DeadlineMissed --> [*]
```
![STD1 Screenshot](screenshot/STD1.png)
 
**Key states**: Draft, FeeOutstanding, FeePaid, PackageIncomplete, PackageReady, Submitted, UnderReview, DocsRequested, Accepted, Rejected, Waitlisted, Cancelled, DeadlineMissed (terminal).
 
**Critical transition**: `PackageReady → Submitted` is guarded by three simultaneous conditions — fee confirmed, package complete, deadline not passed — implementing the UC10 «includes» UC8 and UC10 «includes» UC9 use case relationships.
 
**Guard conditions**: `DeadlineMissed` can be entered from Draft, FeeOutstanding, or PackageReady — the deadline check runs daily against all non-submitted applications. `DocsRequested → PackageIncomplete` allows the workflow to resume after an additional documents request without restarting from scratch.
 
**Requirement mapping**: FR5 (status updates with audit trail), FR6 (document upload gates PackageReady), UC8, UC9, UC10, UC11, US012–US019.
 
---
 
### STD2 — Learner Profile
 
The Learner Profile holds the academic record that drives eligibility calculations and forms the basis of application packages.
 
```mermaid
stateDiagram-v2
    [*] --> Creating : Teacher begins profile creation (UC3)
 
    Creating --> Incomplete : Profile saved with missing required fields
    Creating --> Active : Profile saved [all required fields valid AND school ID unique]
    Creating --> DuplicateID : System detects duplicate school ID [UC3-AF1]
 
    DuplicateID --> Creating : Teacher corrects school ID
 
    Incomplete --> Active : Teacher completes missing fields\n[all required fields now present]
 
    Active --> MarksRecorded : Teacher records subject marks (UC4)\n[at least 1 subject mark saved]
    Active --> Inactive : Administrator deactivates profile
 
    MarksRecorded --> RecommendationsGenerated : Teacher triggers engine (UC5)\n[marks for 6 or more subjects present]
    MarksRecorded --> MarksRecorded : Teacher adds or updates a mark
    MarksRecorded --> Inactive : Administrator deactivates
 
    RecommendationsGenerated --> Stale : Teacher updates marks after generation\n[recommendations no longer reflect current data]
    RecommendationsGenerated --> GuidanceComplete : Teacher records guidance session (UC6)
    RecommendationsGenerated --> Inactive : Administrator deactivates
 
    Stale --> RecommendationsGenerated : Teacher regenerates recommendations
 
    GuidanceComplete --> Stale : Teacher updates marks after guidance session
    GuidanceComplete --> Inactive : Administrator deactivates
 
    Inactive --> Active : Administrator reactivates [with reason logged]
    Inactive --> [*] : Learner graduates, record archived
```
![STD2 Screenshot](screenshot/STD2%20.png)
 
**Key states**: Creating, Incomplete, DuplicateID, Active, MarksRecorded, RecommendationsGenerated, Stale, GuidanceComplete, Inactive.
 
**Critical design**: The `Stale` state prevents guidance sessions from being based on outdated eligibility data — if marks are updated after recommendations are generated, the Stale state forces regeneration before the teacher can share results with the learner.
 
**Requirement mapping**: FR1 (create/manage profiles), FR2 (CSV import triggers MarksRecorded), FR3 (recommendations from MarksRecorded), UC3, UC4, UC5, UC6, US004–US009, US011.
 
---
 
### STD3 — User Account
 
The User Account controls access for all seven actor types. Its lifecycle governs authentication, MFA, and security events.
 
```mermaid
stateDiagram-v2
    [*] --> PendingSetup : Administrator creates account (UC15)\n[email and role assigned]
 
    PendingSetup --> Active : User sets initial password\n[password meets complexity rules]
    PendingSetup --> Expired : Account not activated within 48 hours
 
    Expired --> PendingSetup : Administrator resends activation link
 
    Active --> MFARequired : Login attempt for Admin or IT Support role\n[NFR14: MFA enforced for privileged roles]
    Active --> Locked : 3 consecutive failed login attempts\n[US001 acceptance criteria]
    Active --> PasswordReset : User or Administrator initiates password reset
    Active --> Suspended : Administrator suspends account [reason recorded]
 
    MFARequired --> Active : Correct OTP entered within 5 minutes
    MFARequired --> Locked : OTP entered incorrectly 3 times
 
    Locked --> Active : Administrator unlocks [audit log entry created]
    Locked --> Suspended : Remains locked for more than 24 hours
 
    PasswordReset --> Active : New password set [meets complexity requirements]
 
    Suspended --> Active : Administrator reinstates [reason recorded]
    Suspended --> [*] : Account permanently deleted [POPIA retention rule applied]
 
    Active --> [*] : Account deleted by Administrator
```
![STD3 Screenshot](screenshot/STD3%20.png)
 
**Key states**: PendingSetup, Active, MFARequired, Locked, PasswordReset, Suspended, Expired.
 
**Critical design**: The `Active → MFARequired` transition applies only to Admin and IT Support roles (NFR14). Teachers and learners proceed directly to token issuance. `Locked → Suspended` prevents indefinitely locked accounts from cluttering the active user list.
 
**Requirement mapping**: FR10 (RBAC), FR15 (audit log on every transition), NFR14 (MFA), UC1, UC15, US001, US002, US003.
 
---
 
### STD4 — University Programme
 
The Programme object is published by University Admissions and consumed by the recommendation engine and learner programme browser.
 
```mermaid
stateDiagram-v2
    [*] --> Draft : Admissions Officer starts programme entry (UC2)
 
    Draft --> Published : Officer clicks Publish\n[all fields present AND deadline not in past]
    Draft --> Draft : Officer saves without all fields complete
 
    Published --> UnderEdit : Officer edits a live programme [UC2-AF3]
    Published --> Expired : Application deadline passes [system-triggered daily]
    Published --> Deactivated : Officer or Admin deactivates manually
 
    UnderEdit --> Published : Officer saves and republishes\n[version history entry created]
    UnderEdit --> Draft : Officer discards changes
 
    Expired --> Archived : Academic year ends [data retained for history]
    Expired --> Published : Officer extends deadline [new deadline must be future]
 
    Deactivated --> Published : Officer reactivates [must update deadline if expired]
    Deactivated --> Archived : Archived by Admin after two academic years
 
    Archived --> [*]
```
![STD4 Screenshot](screenshot/STD4%20.png)
 
**Key states**: Draft, Published, UnderEdit, Expired, Deactivated, Archived.
 
**Critical design**: `Published → Expired` is system-triggered (runs daily) — this prevents learners from adding expired programmes to their application list (UC7-AF1). `UnderEdit` retains the published version in version history so learners who already selected the programme see consistent data during edits.
 
**Requirement mapping**: UC2 (publish programme), UC5 (engine reads Published programmes only), UC7 (learner browser shows only Published, disables Expired), US007.
 
---
 
### STD5 — Document (Supporting Document / Recommendation Letter)
 
Documents are uploaded by teachers to build application packages. Every document passes through virus scanning before storage.
 
```mermaid
stateDiagram-v2
    [*] --> Uploading : Teacher selects file and clicks Upload (UC9)
 
    Uploading --> VirusScan : File type and size valid\n[type=PDF or DOC or DOCX AND size not more than 5MB]
    Uploading --> Rejected : File type invalid OR size exceeded\n[US016 acceptance criteria]
 
    Rejected --> [*]
 
    VirusScan --> Stored : Scan passes [file is clean]
    VirusScan --> Quarantined : Scan fails [malicious content detected]
 
    Quarantined --> [*] : IT Support notified, file deleted, event logged
 
    Stored --> Unlinked : Document saved but not yet assigned to application
    Stored --> LinkedToApp : Teacher assigns document to application [document type label set]
 
    Unlinked --> LinkedToApp : Teacher links document to application
    Unlinked --> Deleted : Teacher deletes unlinked document
 
    LinkedToApp --> SubmittedWithApp : Learner submits application (UC10)\n[parent application reaches Submitted state]
    LinkedToApp --> Unlinked : Teacher removes document from package
 
    SubmittedWithApp --> ReceivedByUniversity : University downloads package (UC11)
 
    ReceivedByUniversity --> [*]
    Deleted --> [*]
```
![STD5 Screenshot](screenshot/STD5%20.png)
 
**Key states**: Uploading, VirusScan, Stored, Unlinked, LinkedToApp, SubmittedWithApp, ReceivedByUniversity, Rejected, Quarantined.
 
**Critical design**: The `Quarantined` state ensures malicious files never enter the document store. The `LinkedToApp → Unlinked` back-transition allows teachers to remove and replace documents before submission. Once `SubmittedWithApp`, documents cannot be modified.
 
**Requirement mapping**: FR6 (upload, virus scan, secure storage), FR15 (quarantine events logged), NFR13 (security), UC9, UC10, US016, TC009, TC010.
 
---
 
### STD6 — Payment Transaction
 
The Payment Transaction exists for a single fee payment. Its lifecycle is brief but safety-critical — it prevents fraud and double-payments.
 
```mermaid
stateDiagram-v2
    [*] --> Initiated : Learner clicks Pay Fee for a FeeOutstanding application (UC8)
 
    Initiated --> AwaitingGateway : UniMatch redirects to external payment gateway\n[application status = FeeOutstanding]
 
    AwaitingGateway --> Confirmed : Gateway returns success callback\n[payment reference stored in UniMatch, no card data]
    AwaitingGateway --> Declined : Gateway returns failure callback\n[UC8-AF1: insufficient funds or card declined]
    AwaitingGateway --> TimedOut : No gateway response within 30 seconds [UC8-AF2]
    AwaitingGateway --> Bypassed : Programme fee is zero [UC8-AF3: fee step auto-skipped]
 
    Confirmed --> [*] : Application updated to FeePaid, reference stored
    Declined --> [*] : Application remains FeeOutstanding, learner notified
    TimedOut --> [*] : Application remains FeeOutstanding, learner advised to check bank
    Bypassed --> [*] : Application auto-updated to FeePaid
```
![STD6 Screenshot](screenshot/STD6%20.png)
 
**Key states**: Initiated, AwaitingGateway, Confirmed, Declined, TimedOut, Bypassed.
 
**Critical design**: UniMatch stores only the payment reference returned by the gateway — never card details. The `TimedOut` state requires a different system response from `Declined` (UC8-AF2 vs UC8-AF1): a timeout advisory warns the learner not to retry immediately in case the bank already processed the payment.
 
**Requirement mapping**: NFR13 (no card storage), UC8, US014, US015, US029, TC-NFR03.
 
---
 
### STD7 — Notification
 
Notifications are created by system events and delivered through the external email provider with retry logic.
 
```mermaid
stateDiagram-v2
    [*] --> Created : Triggering event occurs\n(deadline approaching, status change, or decision recorded)
 
    Created --> Queued : Recipient contact details exist in system
    Created --> Suppressed : Recipient has no registered contact OR notifications disabled
 
    Queued --> Dispatched : Notification service sends to email provider [provider available]
    Queued --> RetryPending : Email provider unavailable [first attempt failed]
 
    RetryPending --> Dispatched : Retry succeeds [within 3 attempts over 6 hours]
    RetryPending --> Failed : All 3 retry attempts exhausted
 
    Dispatched --> Delivered : Provider confirms delivery to recipient
    Dispatched --> Bounced : Delivery rejected by recipient mail server
 
    Delivered --> Read : User opens notification in portal
    Delivered --> [*] : Email notification, no read receipt available
 
    Bounced --> Failed : No further retry after bounce
    Failed --> [*] : Admin dashboard alert raised, failure logged in audit trail
 
    Read --> [*]
    Suppressed --> [*]
```
![STD7 Screenshot](screenshot/STD7%20.png)
 
**Key states**: Created, Queued, Suppressed, Dispatched, RetryPending, Delivered, Bounced, Read, Failed.
 
**Critical design**: The `RetryPending` state implements the 3-attempt retry mechanism (US021 acceptance criteria). `Failed` triggers an admin dashboard alert — no deadline can pass silently due to a delivery failure. `Suppressed` is distinct from `Failed`: suppression is intentional, failure is a system error.
 
**Requirement mapping**: FR8 (deadline reminders), FR13 (escalating reminders), UC13, US020, US021, US022, US023.
 
---
 
### STD8 — Recommendation Result
 
The Recommendation Result captures the AI eligibility engine's output for a specific learner at a point in time.
 
```mermaid
stateDiagram-v2
    [*] --> Calculating : Teacher triggers generation (UC5)\n[learner has marks AND programmes published]
 
    Calculating --> Generated : Engine completes within 3 seconds [NFR18]
    Calculating --> PartialResult : Fewer than 6 subjects present [UC5-AF1: results shown with caveat]
    Calculating --> Failed : Engine error or timeout
 
    PartialResult --> Generated : Teacher acknowledges caveat and proceeds
 
    Generated --> ViewedByTeacher : Teacher opens recommendations panel
    Generated --> Stale : Teacher updates learner marks after generation\n[results no longer reflect current data]
 
    Stale --> Calculating : Teacher explicitly triggers regeneration
 
    ViewedByTeacher --> SharedWithLearner : Teacher conducts guidance session (UC6)
    ViewedByTeacher --> Stale : Marks updated before guidance session
 
    SharedWithLearner --> UsedForSelection : Learner selects programmes based on results (UC7)
    SharedWithLearner --> Stale : Marks updated after sharing but before selection
 
    UsedForSelection --> Archived : Academic year ends [retained for historical reporting]
 
    Archived --> [*]
    Failed --> [*]
```
![STD8 Screenshot](screenshot/STD8%20.png)
 
**Key states**: Calculating, Generated, PartialResult, Stale, ViewedByTeacher, SharedWithLearner, UsedForSelection, Archived, Failed.
 
**Critical design**: The `Stale` state at three points (after generation, after sharing, and after use) ensures guidance sessions and learner selections are always based on current mark data. This is an emergent state not in the original requirements — it arose from modelling the full lifecycle.
 
**Requirement mapping**: FR3 (generate automatically), FR4 (Guaranteed/Likely/Borderline/Not Eligible categories), NFR18 (3-second response time), UC5, UC6, UC7, US008, US009, US012.
 
---