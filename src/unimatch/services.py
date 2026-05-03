from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID, uuid4

from unimatch.entities import Application, LearnerProfile, Mark, Notification, RecommendationResult, UniversityProgramme
from unimatch.enums import EligibilityEnum, ProgrammeStatusEnum


class ApsCalculator:
    def calculate(self, marks: list[Mark]) -> int:
        if not marks:
            return 0
        points = sorted((m.to_aps_points() for m in marks if m.is_valid()), reverse=True)
        if len(points) < 6:
            return sum(points)
        return sum(points[:6])

    def apply_nsc_scale(self, score: int) -> int:
        m = Mark(mark_id=UUID(int=0), learner_id=UUID(int=0), subject_name="", score=score, exam_type="", academic_year=0)
        return m.to_aps_points()

    def select_top_n(self, marks: list[Mark], n: int) -> list[Mark]:
        return sorted(marks, key=lambda x: x.to_aps_points(), reverse=True)[:n]


class RequirementMatcher:
    def match(self, aps: int, marks: list[Mark], programme: UniversityProgramme) -> bool:
        return aps >= programme.minimum_aps and self.check_subject_requirements(marks, programme)

    def check_subject_requirements(self, marks: list[Mark], programme: UniversityProgramme) -> bool:
        return bool(marks)


class EligibilityClassifier:
    def classify(self, learner_aps: int, minimum_aps: int, subjects_met: bool) -> EligibilityEnum:
        if not subjects_met:
            return EligibilityEnum.NotEligible
        diff = learner_aps - minimum_aps
        if diff >= 4:
            return EligibilityEnum.Guaranteed
        if diff >= 1:
            return EligibilityEnum.Likely
        if diff >= 0:
            return EligibilityEnum.Borderline
        return EligibilityEnum.NotEligible


@dataclass
class RecommendationService:
    aps_calculator: ApsCalculator
    requirement_matcher: RequirementMatcher
    eligibility_classifier: EligibilityClassifier

    def generate_recommendations(
        self,
        learner: LearnerProfile,
        programmes: list[UniversityProgramme],
    ) -> list[RecommendationResult]:
        marks = self.fetch_marks(learner)
        aps = self.aps_calculator.calculate(marks)
        results: list[RecommendationResult] = []
        for p in self.fetch_programmes(programmes):
            if p.status != ProgrammeStatusEnum.Published:
                continue
            subjects_met = self.requirement_matcher.check_subject_requirements(marks, p)
            eligible = self.requirement_matcher.match(aps, marks, p)
            cat = self.eligibility_classifier.classify(aps, p.minimum_aps, subjects_met and eligible)
            results.append(
                RecommendationResult(
                    result_id=uuid4(),
                    learner_id=learner.learner_id,
                    programme_id=p.programme_id,
                    eligibility_category=cat,
                    learner_aps=aps,
                    programme_minimum_aps=p.minimum_aps,
                )
            )
        return results

    def fetch_marks(self, learner: LearnerProfile) -> list[Mark]:
        return list(learner.marks)

    def fetch_programmes(self, programmes: list[UniversityProgramme]) -> list[UniversityProgramme]:
        return [p for p in programmes if p.application_deadline >= date.today()]


@dataclass
class NotificationService:
    def check_deadlines(self, applications: list[Application], programmes: dict[UUID, UniversityProgramme]) -> None:
        for app in applications:
            prog = programmes.get(app.programme_id)
            if prog and date.today() >= prog.application_deadline:
                continue

    def dispatch(self, notification: Notification) -> None:
        notification.dispatch()

    def retry(self, notification: Notification) -> None:
        notification.retry()

    def build_message(self, type: str, context: dict[str, Any]) -> str:
        return f"{type}:{context.get('summary', '')}"


@dataclass
class Report:
    title: str
    rows: list[dict[str, Any]]


@dataclass
class AnonData:
    buckets: dict[str, int]


@dataclass
class ExportFile:
    name: str
    body: bytes


class ReportingService:
    def generate_report(self, filters: dict[str, Any], role: str) -> Report:
        return Report(title=f"report-{role}", rows=[{"filters": filters}])

    def anonymise(self, data: list[dict[str, Any]]) -> AnonData:
        return AnonData(buckets={"count": len(data)})

    def export_to_csv(self, report: Report) -> ExportFile:
        return ExportFile(name=f"{report.title}.csv", body=b"")

    def export_to_pdf(self, report: Report) -> ExportFile:
        return ExportFile(name=f"{report.title}.pdf", body=b"")
