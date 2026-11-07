# Assignment 8: Activity Workflow Modeling — Activity Diagrams
# UniMatch – School-Based University Application & Eligibility System
 
**Author**: Christinah Mmabotse Mosima
**Date**: 2026-04-15
**Assignment**: 8 – Object State Modeling and Activity Workflow Modeling
 
---
 
## Overview
 
This document defines 8 activity diagrams for the most complex workflows in UniMatch. Each diagram uses swimlanes to show which actor is responsible for each action, includes decision points with explicit branching logic, and identifies parallel actions where the system performs concurrent operations.
 
---
## 2. Activity Diagrams
 
---
 
### AD1 — User Login and Authentication
 
**Workflow**: A user logs in. The system validates credentials, enforces MFA for Admin and IT roles, and routes to the role-appropriate dashboard.
 
```mermaid
flowchart TD
    Start([Start]) --> EnterCredentials
 
    subgraph User [User - Any Role]
        EnterCredentials[Enter email and password]
        EnterOTP[Enter OTP code]
        SetPassword[Set initial password on first login]
    end
 
    subgraph System [UniMatch System - Auth Controller]
        ValidateCredentials{Credentials valid?}
        CheckFirstLogin{First login?}
        CheckRole{Role = Admin or IT?}
        SendOTP[Generate and send OTP via email]
        ValidateOTP{OTP correct and not expired?}
        IncrementFailures[Increment failed login counter]
        CheckLockout{3 or more failed attempts?}
        LockAccount[Lock account and log to audit trail]
        IssueJWT[Issue JWT with role claim]
        RouteToDashboard[Route to role-appropriate dashboard]
        ShowError[Show error: Invalid credentials]
        ShowLockError[Show error: Account locked - contact administrator]
        ShowOTPError[Show error: Invalid or expired OTP]
    end
 
    EnterCredentials --> ValidateCredentials
    ValidateCredentials -- Yes --> CheckFirstLogin
    ValidateCredentials -- No --> IncrementFailures --> CheckLockout
    CheckLockout -- Yes --> LockAccount --> ShowLockError --> End1([End])
    CheckLockout -- No --> ShowError --> EnterCredentials
 
    CheckFirstLogin -- Yes --> SetPassword --> CheckRole
    CheckFirstLogin -- No --> CheckRole
 
    CheckRole -- Yes --> SendOTP --> EnterOTP --> ValidateOTP
    CheckRole -- No --> IssueJWT
 
    ValidateOTP -- Yes --> IssueJWT
    ValidateOTP -- No --> ShowOTPError --> EnterOTP
 
    IssueJWT --> RouteToDashboard --> End2([End])
```
![AD1 Screenshot](screenshot/AD1%20.png)
 
**Swimlanes**: User (any role), UniMatch System (Auth Controller).
 
**Decisions**: Credential validity, first-login detection, role-based MFA check, OTP validation, lockout threshold.
 
**Parallel actions**: OTP email dispatch and display of the OTP entry form occur simultaneously — the user sees the form immediately while the email is being sent in the background.
 
**Stakeholder concern addressed**: Account lockout (3 failures) addresses IT Support's security compliance requirement. MFA branch (NFR14) protects privileged accounts. Role-aware routing meets NFR2 (3-click task completion from dashboard).
 
**Requirement mapping**: FR10, FR15, NFR14, UC1, UC15, US001, US002, US003.
 
---
 
### AD2 — Import Learner Marks via CSV
 
**Workflow**: A teacher uploads a CSV file of learner marks. The system validates, previews, and imports valid records while reporting per-row errors.
 
```mermaid
flowchart TD
    Start([Start]) --> SelectFile
 
    subgraph Teacher [Teacher / Counselor]
        SelectFile[Select CSV file from device]
        ReviewPreview[Review preview: valid rows green, error rows red]
        ConfirmImport[Click Confirm Import]
        DownloadErrors[Optionally download error report CSV]
    end
 
    subgraph System [UniMatch System - Learner Controller]
        ValidateFormat{Valid .csv file extension?}
        ParseCSV[Parse CSV: check headers, data types, value ranges 0 to 100]
        FlagErrors[Flag invalid rows with per-row error codes]
        GeneratePreview[Generate preview with error annotations]
        CheckAnyValid{At least 1 valid row?}
        SaveValidRows[Save valid rows to database]
        CreateAudit[Create audit log entry: user ID, timestamp, counts]
        GenerateSummary[Display summary: Imported X, Skipped Y, Errors Z]
        ShowFormatError[Show error: Invalid file format - please upload .csv]
        ShowNoValid[Show message: No valid records found - check error report]
    end
 
    SelectFile --> ValidateFormat
    ValidateFormat -- No --> ShowFormatError --> SelectFile
    ValidateFormat -- Yes --> ParseCSV --> FlagErrors --> GeneratePreview --> ReviewPreview
    ReviewPreview --> CheckAnyValid
    CheckAnyValid -- No --> ShowNoValid --> DownloadErrors --> End1([End])
    CheckAnyValid -- Yes --> ConfirmImport --> SaveValidRows
 
    SaveValidRows --> CreateAudit
    SaveValidRows --> GenerateSummary
 
    CreateAudit --> End2([End])
    GenerateSummary --> DownloadErrors --> End2
```
![AD2 Screenshot](screenshot/AD2%20.png)
 
**Swimlanes**: Teacher / Counselor, UniMatch System (Learner Controller).
 
**Parallel actions**: After the teacher confirms, `SaveValidRows` triggers both `CreateAudit` and `GenerateSummary` concurrently — data is persisted while the summary is rendered.
 
**Decisions**: File format validation, invalid row detection, minimum valid row check.
 
**Stakeholder concern addressed**: Teachers' pain point of "time-consuming manual data entry" — bulk import replaces row-by-row entry. Per-row error report (TC004) lets teachers fix specific problems without re-uploading the entire file.
 
**Requirement mapping**: FR2, NFR20, UC4, US006, TC003, TC004.
 
---
 
### AD3 — Generate AI Eligibility Recommendations
 
**Workflow**: The full recommendation pipeline from teacher trigger through ranked results with explanation factors.
 
```mermaid
flowchart TD
    Start([Start]) --> OpenProfile
 
    subgraph Teacher [Teacher / Counselor]
        OpenProfile[Open learner profile]
        ClickGenerate[Click Generate Recommendations]
        AcknowledgeCaveat[Acknowledge incomplete data caveat]
        ReviewResults[Review ranked list with explanation factors]
        FilterResults[Apply filters: university, faculty, category]
    end
 
    subgraph Engine [Recommendation Engine Service]
        FetchMarks[Fetch learner mark records from database]
        CheckMarkCount{Marks for 6 or more subjects?}
        AddCaveat[Add caveat flag: results based on incomplete data]
        FetchProgrammes[Fetch all active published programmes]
        CheckProgrammes{Programmes available?}
        CalcAPS[ApsCalculator: sum top N subjects per SA APS formula]
        MatchReqs[RequirementMatcher: compare APS and subjects vs each programme]
        ClassifyResults[EligibilityClassifier: assign Guaranteed, Likely, Borderline, or Not Eligible]
        BuildExplanations[Build explanation per result: subject match and gap details]
        RankResults[Sort: Guaranteed first, then Likely, Borderline, Not Eligible]
        SaveResults[Save ranked list and explanations to learner profile with timestamp]
        DisplayResults[Display results within 3 seconds - NFR18]
        ShowNoProgrammes[Show message: No programmes available - universities must publish data]
    end
 
    OpenProfile --> ClickGenerate --> FetchMarks --> CheckMarkCount
    CheckMarkCount -- No --> AddCaveat --> AcknowledgeCaveat --> FetchProgrammes
    CheckMarkCount -- Yes --> FetchProgrammes
    FetchProgrammes --> CheckProgrammes
    CheckProgrammes -- No --> ShowNoProgrammes --> End1([End])
    CheckProgrammes -- Yes --> CalcAPS --> MatchReqs --> ClassifyResults --> BuildExplanations --> RankResults
 
    RankResults --> SaveResults
    RankResults --> DisplayResults
 
    SaveResults --> ReviewResults
    DisplayResults --> ReviewResults
 
    ReviewResults --> FilterResults --> End2([End])
```
![AD3 Screenshot](screenshot/AD3%20.png)
 
**Swimlanes**: Teacher / Counselor, Recommendation Engine Service (matching ARCHITECTURE.md §4–5 component names: ApsCalculator, RequirementMatcher, EligibilityClassifier).
 
**Parallel actions**: `SaveResults` and `DisplayResults` execute concurrently after ranking — the database write and UI render happen simultaneously so the 3-second NFR18 target is not blocked by persistence.
 
**Decisions**: Minimum subject count (6 required for reliable APS), programme availability.
 
**Stakeholder concern addressed**: Replaces teacher's manual spreadsheet APS calculations (STAKEHOLDER_ANALYSIS.md pain point). Explanation factors address AI ethics concern — no opaque scores, every result is explainable to the learner.
 
**Requirement mapping**: FR3, FR4, NFR18, UC5, US008, US009, TC005, TC006, TC-NFR05.
 
---
 
### AD4 — Learner Programme Selection and Fee Payment
 
**Workflow**: The learner browses programmes, selects one, and completes fee payment through the external gateway.
 
```mermaid
flowchart TD
    Start([Start]) --> OpenExplorer
 
    subgraph Learner [Learner]
        OpenExplorer[Open Programme Explorer]
        Browse[Browse and filter programmes by eligibility, university, deadline]
        ViewDetails[View programme details: APS req, subjects, deadline, fee]
        ClickAdd[Click Add to my applications]
        AcknowledgeWarning[Acknowledge eligibility warning and confirm]
        ClickPay[Click Pay fee on application]
        CompleteAtGateway[Complete payment form at gateway page]
    end
 
    subgraph System [UniMatch System]
        CheckDeadline{Programme deadline passed?}
        CheckDuplicate{Programme already in application list?}
        CheckEligibility{Eligibility = Borderline or Not Eligible?}
        ShowWarning[Show eligibility warning with contributing factors]
        CreateDraft[Create Application record - status = FeeOutstanding]
        CheckFeeZero{Application fee = zero?}
        AutoBypass[Auto-update status to FeePaid - zero fee programme]
        RedirectGateway[Redirect to external payment gateway - no card data stored]
        ReceiveCallback{Gateway callback received within 30 seconds?}
        CheckResult{Payment successful?}
        UpdateFeePaid[Update status to FeePaid - store payment reference only]
        ShowDeadlinePassed[Show message: Application deadline has passed]
        ShowDuplicate[Show message: Programme already in your list]
        ShowDecline[Show message: Payment unsuccessful - please try again]
        ShowTimeout[Show message: Payment timed out - check bank before retrying]
    end
 
    subgraph Gateway [External Payment Gateway]
        ProcessPayment[Process card payment securely - UniMatch never sees card details]
    end
 
    OpenExplorer --> Browse --> ViewDetails --> ClickAdd
    ClickAdd --> CheckDeadline
    CheckDeadline -- Yes --> ShowDeadlinePassed --> End1([End])
    CheckDeadline -- No --> CheckDuplicate
    CheckDuplicate -- Yes --> ShowDuplicate --> Browse
    CheckDuplicate -- No --> CheckEligibility
    CheckEligibility -- Yes --> ShowWarning --> AcknowledgeWarning --> CreateDraft
    CheckEligibility -- No --> CreateDraft
 
    CreateDraft --> CheckFeeZero
    CheckFeeZero -- Yes --> AutoBypass --> End2([End])
    CheckFeeZero -- No --> ClickPay --> RedirectGateway --> ProcessPayment
 
    ProcessPayment --> ReceiveCallback
    ReceiveCallback -- Timeout --> ShowTimeout --> End3([End])
    ReceiveCallback -- Yes --> CheckResult
    CheckResult -- Success --> UpdateFeePaid --> End4([End])
    CheckResult -- Failure --> ShowDecline --> ClickPay
```
![AD4 Screenshot](screenshot/AD4%20.png)
 
**Swimlanes**: Learner, UniMatch System, External Payment Gateway (separate swimlane — outside UniMatch boundary).
 
**Parallel actions**: Not present — payment is a sequential safety-critical flow where each step must complete before the next begins.
 
**Decisions**: Deadline check, duplicate detection, eligibility warning, zero-fee bypass, gateway timeout, payment result.
 
**Stakeholder concern addressed**: Gateway swimlane separation makes the anti-fraud design explicit: UniMatch never touches card data (TC-NFR03, US029). Learner autonomy preserved — Borderline/Not Eligible selections warn but do not block (UC7-AF2).
 
**Requirement mapping**: UC7, UC8, NFR13, US012–US015, US029, TC-NFR03.
 
---
 
### AD5 — Compile Application Package and Submit
 
**Workflow**: Teacher compiles the application package, learner reviews it, and the application is submitted to the university.
 
```mermaid
flowchart TD
    Start([Start]) --> OpenApp
 
    subgraph Teacher [Teacher / Counselor]
        OpenApp[Open application with status FeePaid]
        UploadDocs[Upload required documents: recommendation letter, transcript, ID copy]
        MarkReady[Mark package as ready for learner review]
    end
 
    subgraph Learner [Learner]
        ReviewPackage[Review compiled package: transcript, documents, letters]
        ConfirmSubmit[Click Submit Application]
    end
 
    subgraph System [UniMatch System]
        ScanDoc[Virus scan each uploaded file]
        CheckDocType{File type PDF, DOC, or DOCX?}
        StoreDoc[Store file securely - record metadata: name, type, uploader, date]
        CheckAllDocs{All required documents present?}
        FlagMissing[Flag missing documents on package status]
        PreCheck{Fee confirmed AND package complete AND deadline not passed?}
        ShowBlocker[Show blocked message with specific reason]
        Transmit[Transmit package to university via integration interface]
        CheckIntegration{University system available?}
        UpdateSubmitted[Update status to Submitted - store acknowledgement reference]
        QueueRetry[Queue application - retry automatically - notify learner of delay]
        NotifyLearner[Send confirmation notification to learner]
        NotifyTeacher[Send confirmation notification to teacher]
        CreateAudit[Create audit log entry: submission details and timestamp]
    end
 
    subgraph University [University Integration]
        ReceivePackage[Receive application package and return acknowledgement reference]
    end
 
    OpenApp --> UploadDocs --> ScanDoc --> CheckDocType
    CheckDocType -- No --> End1([End - file rejected])
    CheckDocType -- Yes --> StoreDoc --> CheckAllDocs
    CheckAllDocs -- No --> FlagMissing --> MarkReady
    CheckAllDocs -- Yes --> MarkReady --> ReviewPackage --> ConfirmSubmit
 
    ConfirmSubmit --> PreCheck
    PreCheck -- No --> ShowBlocker --> End2([End - blocked])
    PreCheck -- Yes --> Transmit --> ReceivePackage --> CheckIntegration
    CheckIntegration -- No --> QueueRetry --> End3([End - queued])
    CheckIntegration -- Yes --> UpdateSubmitted
 
    UpdateSubmitted --> NotifyLearner
    UpdateSubmitted --> NotifyTeacher
    UpdateSubmitted --> CreateAudit
 
    NotifyLearner --> End4([End - submitted])
    NotifyTeacher --> End4
    CreateAudit --> End4
```
![AD5 Screenshot](screenshot/AD5%20.png)
 
**Swimlanes**: Teacher / Counselor, Learner, UniMatch System, University Integration.
 
**Parallel actions**: After `UpdateSubmitted`, `NotifyLearner`, `NotifyTeacher`, and `CreateAudit` execute concurrently — the learner and teacher receive confirmation simultaneously, and the audit entry is written at the same time.
 
**Decisions**: File type validation, document completeness check, pre-submission triple guard (fee + documents + deadline), university system availability.
 
**Stakeholder concern addressed**: University Admissions' concern about incomplete applications — CheckAllDocs physically blocks submission until every required document is present. The QueueRetry path (UC10-AF3) prevents data loss if the university integration is temporarily unavailable.
 
**Requirement mapping**: FR5, FR6, UC9, UC10, US016–US018, TC008, TC009, TC010.
 
---
 
### AD6 — University Admissions Review and Decision
 
**Workflow**: A University Admissions Officer reviews a submitted application and records an official admission decision.
 
```mermaid
flowchart TD
    Start([Start]) --> Login
 
    subgraph Officer [University Admissions Officer]
        Login[Log in with University Admissions role]
        OpenIncoming[Open Incoming Applications for this institution]
        SelectApp[Select an application to review]
        ReviewPackage[Review: transcript, APS score, documents, recommendation letters, AI category advisory]
        RecordDecision[Select decision: Accept, Reject, Waitlist, or Request Additional Documents]
        SpecifyDocs[Specify which documents are required]
        AddNote[Add optional decision note]
        ConfirmDecision[Click Confirm Decision]
    end
 
    subgraph System [UniMatch System]
        CheckScope{Application belongs to this institution?}
        Return403[Return HTTP 403 Forbidden]
        ShowAIAdvisory[Display AI eligibility category as advisory only - system does not influence decision]
        ValidateDecision{Decision selected?}
        CheckDocRequest{Decision = Request Additional Documents?}
        SaveDecision[Save decision: officer ID, decision, timestamp, note]
        UpdateStatus[Update application status]
        NotifyLearner[Send notification to learner via portal and email]
        NotifyTeacher[Send notification to teacher via email]
        CreateAudit[Create audit log entry with full decision context]
    end
 
    Login --> OpenIncoming --> SelectApp --> CheckScope
    CheckScope -- No --> Return403 --> End1([End])
    CheckScope -- Yes --> ShowAIAdvisory --> ReviewPackage --> RecordDecision
 
    RecordDecision --> CheckDocRequest
    CheckDocRequest -- Yes --> SpecifyDocs --> AddNote --> ConfirmDecision
    CheckDocRequest -- No --> AddNote --> ConfirmDecision
 
    ConfirmDecision --> ValidateDecision
    ValidateDecision -- No --> RecordDecision
    ValidateDecision -- Yes --> SaveDecision --> UpdateStatus
 
    UpdateStatus --> NotifyLearner
    UpdateStatus --> NotifyTeacher
    UpdateStatus --> CreateAudit
 
    NotifyLearner --> End2([End])
    NotifyTeacher --> End2
    CreateAudit --> End2
```
![AD6 Screenshot](screenshot/AD6%20.png)
 
**Swimlanes**: University Admissions Officer, UniMatch System.
 
**Parallel actions**: After `UpdateStatus`, `NotifyLearner`, `NotifyTeacher`, and `CreateAudit` execute concurrently — learner and teacher receive outcomes simultaneously without sequential delay.
 
**Decisions**: Institution scope check (HTTP 403 enforces data isolation), decision type (whether additional documents are needed), decision validation.
 
**Critical design**: `ShowAIAdvisory` is a deliberate system step — the AI eligibility category is displayed for officer reference but marked advisory only. The system does not pre-filter or rank applications by this category. Decision authority belongs to the university (Assignment 5, Decision Authority Matrix §2.2).
 
**Requirement mapping**: FR5, FR15, UC11, US018, US019, TC007, TC014.
 
---
 
### AD7 — Generate and Export Analytics Report
 
**Workflow**: A School Administrator or DoE Official generates an analytics report. PII anonymisation is enforced structurally for government exports.
 
```mermaid
flowchart TD
    Start([Start]) --> NavigateReports
 
    subgraph User [Administrator or DoE Official]
        NavigateReports[Navigate to Reports section]
        SelectType[Select report type: Application Summary, Placement Rate, DoE Anonymised Export]
        SetFilters[Set filters: date range, grade, counselor, school]
        ClickGenerate[Click Generate Report]
        PreviewReport[Preview report on screen]
        SelectFormat[Select export format: PDF or CSV]
        Download[Download file]
    end
 
    subgraph System [UniMatch System - Reporting Service]
        CheckRole{User role = DoE or District?}
        EnforceAnon[Strip all PII: no names, IDs, or contact details. Apply k-anonymity: cells under 5 shown as less than 5]
        AggregateData[Aggregate learner and application data per filter parameters]
        CheckSize{Record count above 5000?}
        ProcessAsync[Process asynchronously - email download link when ready]
        GenerateReport[Generate report synchronously within 60 seconds]
        RenderPreview[Render on-screen preview]
        GeneratePDF[Generate PDF file]
        GenerateCSV[Generate CSV file - no PII if DoE export]
        LogExport[Log export: user ID, report type, filters, timestamp]
    end
 
    NavigateReports --> SelectType --> CheckRole
    CheckRole -- Yes DoE or District --> EnforceAnon --> SetFilters
    CheckRole -- No Admin --> SetFilters
 
    SetFilters --> ClickGenerate --> AggregateData --> CheckSize
    CheckSize -- Yes --> ProcessAsync --> End1([End - async])
    CheckSize -- No --> GenerateReport --> RenderPreview --> PreviewReport
 
    PreviewReport --> SelectFormat
    SelectFormat -- PDF --> GeneratePDF --> LogExport --> Download --> End2([End])
    SelectFormat -- CSV --> GenerateCSV --> LogExport --> Download --> End2
```
![AD7 Screenshot](screenshot/AD7%20.png)
 
**Swimlanes**: Administrator or DoE Official, UniMatch System (Reporting Service).
 
**Parallel actions**: Not present in this workflow — export format selection is a sequential decision (PDF or CSV, not both).
 
**Decisions**: Role check for anonymisation (applied once at the start), record volume check for async processing, format selection.
 
**Stakeholder concern addressed**: DoE's requirement for "reliable aggregated statistics without personal data exposure" is enforced structurally — anonymisation is a system step, not a policy. The k-anonymity rule (cells under 5 shown as "< 5") prevents re-identification through small-group inference. This directly implements NFR15 (POPIA compliance).
 
**Requirement mapping**: FR9, FR11, NFR15, UC14, US025, US026, TC013.
 
---
 
### AD8 — Automated Deadline Notification Dispatch
 
**Workflow**: The background job that runs daily, checks all application deadlines, and dispatches escalating reminders.
 
```mermaid
flowchart TD
    Start([Start - Daily 06:00 scheduler]) --> FetchDeadlines
 
    subgraph System [UniMatch System - Notification Service]
        FetchDeadlines[Fetch all active application deadlines from database]
        CheckDeadlines{Any deadlines within 7 days?}
        FilterLearners[For each deadline: find learners with incomplete applications - status not Submitted, Accepted, or Rejected]
        CheckIncomplete{Any incomplete applications found?}
        DetermineUrgency{Days until deadline?}
        Create7Day[Create 7-day reminder for assigned teacher]
        Create3Day[Create 3-day reminder with elevated priority]
        Create1Day[Create 1-day urgent reminder]
        CreateOverdue[Create overdue alert for teacher and admin]
        QueueAll[Add all notifications to dispatch queue]
        DispatchEmails[Dispatch emails via external SMTP provider]
        CheckDelivery{Delivery confirmed?}
        LogSuccess[Log delivery: recipient, timestamp, notification type]
        RetryQueue[Add to retry queue - max 3 attempts at 2-hour intervals]
        CheckRetries{Retry attempts exhausted?}
        RaiseAlert[Raise alert on admin dashboard - log failure in audit trail]
        MarkFailed[Mark notification as Failed]
    end
 
    subgraph Teacher [Teacher / Counselor]
        ReceiveEmail[Receive email listing affected learners and outstanding items]
        TakeAction[Review flagged learners and take action]
    end
 
    FetchDeadlines --> CheckDeadlines
    CheckDeadlines -- No --> End1([End - nothing to send])
    CheckDeadlines -- Yes --> FilterLearners --> CheckIncomplete
    CheckIncomplete -- No --> End1
    CheckIncomplete -- Yes --> DetermineUrgency
 
    DetermineUrgency -- 7 days --> Create7Day --> QueueAll
    DetermineUrgency -- 3 days --> Create3Day --> QueueAll
    DetermineUrgency -- 1 day --> Create1Day --> QueueAll
    DetermineUrgency -- Overdue --> CreateOverdue --> QueueAll
 
    QueueAll --> DispatchEmails --> CheckDelivery
    CheckDelivery -- Yes --> LogSuccess --> ReceiveEmail --> TakeAction --> End2([End])
    CheckDelivery -- No --> RetryQueue --> CheckRetries
    CheckRetries -- No --> DispatchEmails
    CheckRetries -- Yes --> RaiseAlert --> MarkFailed --> End3([End - failed])
```
![AD8 Screenshot](screenshot/AD8%20.png)
 
**Swimlanes**: UniMatch System (Notification Service), Teacher / Counselor.
 
**Parallel actions**: Multiple reminder notifications for different teachers and deadlines are created and queued simultaneously in the `QueueAll` step — the system processes all reminders in a single batch dispatch.
 
**Decisions**: Deadlines within 7 days, incomplete applications exist, urgency level (4 branches: 7-day, 3-day, 1-day, overdue), delivery confirmation, retry exhaustion.
 
**Stakeholder concern addressed**: Teachers' concern about missed application deadlines — no deadline passes silently. Overdue alert also notifies admins, creating an escalation path if the assigned teacher is unavailable.
 
**Requirement mapping**: FR8, FR13, UC13, US020, US021, US022.
 
---
 
## 3. Traceability Matrix
 
| Diagram | FR / NFR | UC | User Story (A6) | Sprint |
|---|---|---|---|---|
| STD1 Application | FR5, FR6 | UC8, UC9, UC10, UC11 | US012–US019 | Sprint 2–3 |
| STD2 Learner Profile | FR1, FR2, FR3, FR4 | UC3, UC4, UC5, UC6 | US004–US009, US011 | Sprint 1–2 |
| STD3 User Account | FR10, FR15, NFR14 | UC1, UC15 | US001–US003 | Sprint 1 |
| STD4 Programme | FR3, FR4 | UC2, UC5, UC7 | US007, US008 | Sprint 1–2 |
| STD5 Document | FR6, FR15, NFR13 | UC9, UC10 | US016 | Sprint 2 |
| STD6 Payment | NFR13 | UC8 | US014, US015, US029 | Sprint 2 |
| STD7 Notification | FR8, FR13 | UC13 | US020–US023 | Sprint 2–3 |
| STD8 Recommendation | FR3, FR4, NFR18 | UC5, UC6, UC7 | US008, US009, US012 | Sprint 1–2 |
| AD1 Login | FR10, FR15, NFR14 | UC1, UC15 | US001–US003 | Sprint 1 |
| AD2 Import CSV | FR2, NFR20 | UC4 | US006 | Sprint 1–2 |
| AD3 Recommendations | FR3, FR4, NFR18 | UC5 | US008, US009 | Sprint 1–2 |
| AD4 Selection and Payment | NFR13 | UC7, UC8 | US012–US015, US029 | Sprint 2–3 |
| AD5 Package and Submit | FR5, FR6 | UC9, UC10 | US016–US018 | Sprint 3 |
| AD6 University Decision | FR5, FR15 | UC11 | US018, US019 | Sprint 3 |
| AD7 Analytics Report | FR9, FR11, NFR15 | UC14 | US025, US026 | Sprint 4 |
| AD8 Notifications | FR8, FR13 | UC13 | US020–US022 | Sprint 2 |
 
---