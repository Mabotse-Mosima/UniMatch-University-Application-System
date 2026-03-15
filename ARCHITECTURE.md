# ARCHITECTURE – UniMatch: School-Based University Application & Eligibility System

Author: Mmabotse Mosima  
Date: 2025-12-01  
Version: 1.0

---

## 1. Introduction

- **Project Title**: UniMatch – School-Based University Application & Eligibility System  
- **Domain**: School administration and higher-education guidance (South African high schools).  
- **Problem Statement**: Schools need a centralized, school-operated platform to manage learner application data, eligibility, recommendation letters, and reporting.  
- **Individual Scope / Feasibility**: A single-school, web-based solution with one frontend (React), one backend API (Node.js/Express), and a relational database (PostgreSQL) is realistic for an individual student over one semester.

This document presents the architecture using the **C4 model** (Context, Container, and Component diagrams) with Mermaid.

---

## 2. C4 Level 1 – System Context Diagram
![UniMatch Level 1 Context](screenshot/level%201.png)

```mermaid
C4Context
title UniMatch - System Context Diagram

Person(teacher, "Teacher / Counselor", "Enters learner marks, tracks applications, uploads documents.")
Person(admin, "School Administrator", "Oversees all learners, configures programmes, generates reports.")
Person(government, "Government / District Official", "Views anonymized, aggregated statistics (read-only).")

System_Boundary(unimatch, "UniMatch System") {
  System(unimatch_web, "UniMatch Web Application", "School-based university application & eligibility tracking system.")
}

System_Ext(university_portals, "University Portals", "External university systems for online applications (future).")
System_Ext(email_service, "Email Service", "External service for sending email notifications.")

Rel(teacher, unimatch_web, "Uses for learner management and recommendations", "HTTPS")
Rel(admin, unimatch_web, "Uses for full oversight and configuration", "HTTPS")
Rel(government, unimatch_web, "Uses for anonymized reports", "HTTPS")

Rel(unimatch_web, university_portals, "Potential future integration for submitting applications", "HTTPS (planned)")
Rel(unimatch_web, email_service, "Sends email reminders to staff", "SMTP/HTTPS")


## 3. C4 Level 2 – Container Diagram
![UniMatch Level 2 Container](screenshot/level%202.png)

```mermaid
C4Container
title UniMatch - Container Diagram

Person(teacher, "Teacher / Counselor", "Tracks learners and applications.")
Person(admin, "School Administrator", "Oversees system and reports.")
Person(government, "Government / District Official", "Views aggregated stats.")

System_Boundary(unimatch, "UniMatch System") {
  Container(webapp, "Web Frontend", "React (TypeScript)", "UI for staff.")
  Container(api, "Backend API", "Node.js / Express", "Business logic and REST API.")
  ContainerDb(db, "Relational Database", "PostgreSQL", "Stores core data.")
  Container(files, "Document Storage", "File store / Object store", "Stores uploaded documents.")
  Container(notify, "Notification Module", "Node.js module", "Sends alerts and reminders.")
}

System_Ext(email_service, "Email Service", "SMTP/Email provider")

Rel(teacher, webapp, "Uses via browser", "HTTPS")
Rel(admin, webapp, "Uses via browser", "HTTPS")
Rel(government, webapp, "Uses via browser", "HTTPS")

Rel(webapp, api, "REST (JSON)", "HTTPS")
Rel(api, db, "Reads/Writes", "SQL/TCP")
Rel(api, files, "Stores/Retrieves files", "File/Blob")
Rel(api, notify, "Triggers notifications", "Internal")
Rel(notify, email_service, "Sends emails", "SMTP/HTTPS")
Rel(notify, db, "Reads deadlines/status", "SQL/TCP")

## 4. C4 Level 3 – Component Diagram (Backend API)
![UniMatch Level 3 Component](screenshot/level%203.png)

```mermaid
C4Component
title UniMatch - Backend API Components
Container_Boundary(api, "Backend API (Node.js / Express)") {
  Component(authCtrl, "Auth Controller", "Express Controller", "Handles login, token issuance, and basic role checks.")
  Component(userCtrl, "User Management Controller", "Express Controller", "Manages user accounts and roles.")
  Component(learnerCtrl, "Learner Controller", "Express Controller", "Manages learners, subjects, marks, and counselor assignments.")
  Component(appCtrl, "Application Controller", "Express Controller", "Manages university applications and their statuses.")
  Component(docCtrl, "Document Controller", "Express Controller", "Handles upload/download of learner documents and links them to learners.")
  Component(recCtrl, "Recommendation Controller", "Express Controller", "Exposes endpoints to trigger and retrieve programme recommendations for learners.")
  Component(reportCtrl, "Reporting Controller", "Express Controller", "Provides dashboard data and exportable reports.")
  Component(recService, "Recommendation Engine Service", "Service", "Computes APS scores, checks requirements, and ranks programmes by eligibility.")
  Component(reportService, "Reporting Service", "Service", "Aggregates statistics for dashboards and anonymized reports.")
  Component(notifyService, "Notification Service", "Service", "Checks deadlines and missing data, creates alerts and dispatches email notifications.")
  Component(repoLayer, "Repository Layer", "Data Access Layer", "Provides repositories for Learners, Marks, Programmes, Applications, Documents, Notifications, and Users.")
}
ContainerDb(db, "Relational Database", "PostgreSQL")
Rel(authCtrl, repoLayer, "Validates user credentials and loads roles", "SQL")
Rel(userCtrl, repoLayer, "Creates and updates user records", "SQL")
Rel(learnerCtrl, repoLayer, "CRUD learners, subjects, and marks", "SQL")
Rel(appCtrl, repoLayer, "CRUD applications and status history", "SQL")
Rel(docCtrl, repoLayer, "Stores and retrieves document metadata", "SQL")
Rel(recCtrl, recService, "Requests eligibility calculations and results")
Rel(recService, repoLayer, "Reads learners, marks, and programme requirements", "SQL")
Rel(reportCtrl, reportService, "Requests dashboard/summary data and exports")
Rel(reportService, repoLayer, "Reads application and learner aggregates", "SQL")
Rel(notifyService, repoLayer, "Reads deadlines, statuses, and user contact info", "SQL")
Rel(repoLayer, db, "Reads/Writes all persistent data", "SQL/TCP")

## 5. C4 Level 4 – Code Diagram (Recommendation Engine)
![UniMatch Level 4 Code Diagram](screenshot/level%204.png)

```mermaid
classDiagram
    class RecommendationService {
        +generateRecommendations(learnerId)
        -calculateAps(marks)
        -rankProgrammes(matches)
    }

    class ApsCalculator {
        +calculate(marks) int
    }

    class RequirementMatcher {
        +match(aps, subjects, programmes) ProgrammeMatch[]
    }

    class EligibilityClassifier {
        +classify(match) EligibilityCategory
    }

    class RecommendationMapper {
        +toDto(recommendations) RecommendationDto[]
    }

    class ProgrammeRepository {
        +getProgrammes() Programme[]
    }

    class LearnerRepository {
        +getLearnerMarks(learnerId) Mark[]
    }

    RecommendationService --> ApsCalculator : uses
    RecommendationService --> RequirementMatcher : uses
    RecommendationService --> EligibilityClassifier : uses
    RecommendationService --> RecommendationMapper : uses
    RecommendationService --> ProgrammeRepository : reads
    RecommendationService --> LearnerRepository : reads


## 6. End-to-End Example Flow

**Scenario**: Teacher generates university recommendations for a learner.

1. The Teacher logs into the **Web Frontend** (React) and opens a learner profile.
2. The frontend calls the **Backend API** (`Learner Controller`) to fetch learner data and marks from the **Database** via the **Repository Layer**.
3. The Teacher clicks “Generate Recommendations”.
4. The frontend sends a request to the **Recommendation Controller** in the Backend API.
5. **Recommendation Controller** calls the **Recommendation Engine Service**, which:
   - Reads learner marks and programme requirements from the **Database** via the **Repository Layer**.
   - Calculates APS and compares it to programme requirements.
   - Assigns eligibility categories (Guaranteed/Likely/Borderline/Not Eligible).
6. The **Recommendation Engine Service** returns a ranked list to the **Recommendation Controller**, which returns it as JSON to the frontend.
7. The **Web Frontend** displays the ranked recommendations to the Teacher on the learner’s profile.

This shows how all main components (frontend, controllers, services, repository, database) work together end-to-end.