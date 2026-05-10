from __future__ import annotations

from enum import Enum


class RoleEnum(Enum):
    Teacher = "Teacher"
    SchoolAdmin = "SchoolAdmin"
    Learner = "Learner"
    Parent = "Parent"
    UniversityAdmissions = "UniversityAdmissions"
    DoEOfficial = "DoEOfficial"
    ITSupport = "ITSupport"


class ApplicationStatusEnum(Enum):
    Draft = "Draft"
    FeeOutstanding = "FeeOutstanding"
    FeePaid = "FeePaid"
    PackageIncomplete = "PackageIncomplete"
    PackageReady = "PackageReady"
    Submitted = "Submitted"
    UnderReview = "UnderReview"
    DocsRequested = "DocsRequested"
    Accepted = "Accepted"
    Rejected = "Rejected"
    Waitlisted = "Waitlisted"
    Cancelled = "Cancelled"
    DeadlineMissed = "DeadlineMissed"


class EligibilityEnum(Enum):
    Guaranteed = "Guaranteed"
    Likely = "Likely"
    Borderline = "Borderline"
    NotEligible = "NotEligible"


class ProgrammeStatusEnum(Enum):
    Draft = "Draft"
    Published = "Published"
    UnderEdit = "UnderEdit"
    Expired = "Expired"
    Deactivated = "Deactivated"
    Archived = "Archived"


class PaymentStatusEnum(Enum):
    Initiated = "Initiated"
    AwaitingGateway = "AwaitingGateway"
    Confirmed = "Confirmed"
    Declined = "Declined"
    TimedOut = "TimedOut"
    Bypassed = "Bypassed"


class ProfileStatusEnum(Enum):
    Creating = "Creating"
    Incomplete = "Incomplete"
    Active = "Active"
    MarksRecorded = "MarksRecorded"
    RecommendationsGenerated = "RecommendationsGenerated"
    Stale = "Stale"
    GuidanceComplete = "GuidanceComplete"
    Inactive = "Inactive"
