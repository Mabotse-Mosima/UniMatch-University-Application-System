"""UniMatch domain package (Assignment 10 class diagram implementation)."""

from unimatch.entities import (
    Application,
    AuditLogEntry,
    Document,
    LearnerProfile,
    Mark,
    Notification,
    PaymentTransaction,
    RecommendationResult,
    UniversityProgramme,
    UserAccount,
)
from unimatch.enums import (
    ApplicationStatusEnum,
    EligibilityEnum,
    PaymentStatusEnum,
    ProfileStatusEnum,
    ProgrammeStatusEnum,
    RoleEnum,
)
from unimatch.services import (
    ApsCalculator,
    EligibilityClassifier,
    NotificationService,
    RecommendationService,
    ReportingService,
    RequirementMatcher,
)
from unimatch.status_history import StatusHistoryEntry

__all__ = [
    "Application",
    "ApplicationStatusEnum",
    "AuditLogEntry",
    "ApsCalculator",
    "Document",
    "EligibilityClassifier",
    "EligibilityEnum",
    "LearnerProfile",
    "Mark",
    "Notification",
    "NotificationService",
    "PaymentStatusEnum",
    "PaymentTransaction",
    "ProfileStatusEnum",
    "ProgrammeStatusEnum",
    "RecommendationResult",
    "RecommendationService",
    "ReportingService",
    "RequirementMatcher",
    "RoleEnum",
    "StatusHistoryEntry",
    "UniversityProgramme",
    "UserAccount",
]
