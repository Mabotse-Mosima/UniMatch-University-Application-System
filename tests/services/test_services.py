"""
tests/services/test_services.py
================================
Unit tests for the three UniMatch service classes.

Tests cover all business rules:
  - LearnerProfileService  (create, get, update, delete, add_mark, aps, deactivate)
  - UniversityProgrammeService (CRUD, publish, deactivate, eligibility, edge cases)
  - ApplicationService     (create, cap at 5, duplicate guard, cancel, status update)
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from unimatch.entities import (
    Application,
    LearnerProfile,
    Mark,
    NSC_DEFAULT_SCORING_RULE,
    ScoringRule,
    UniversityProgramme,
    calc_aps_for_university,
)
from unimatch.enums import (
    ApplicationStatusEnum,
    EligibilityEnum,
    ProfileStatusEnum,
    ProgrammeStatusEnum,
)
from unimatch.repositories.inmemory import (
    InMemoryApplicationRepository,
    InMemoryLearnerProfileRepository,
    InMemoryScoringRuleRepository,
    InMemoryUniversityProgrammeRepository,
)
from unimatch.services import (
    ApplicationNotFoundError,
    ApplicationService,
    DuplicateApplicationError,
    InvalidStatusTransitionError,
    LearnerNotFoundError,
    LearnerProfileService,
    NotEligibleError,
    ProgrammeNotActiveError,
    ProgrammeNotFoundError,
    UniversityProgrammeService,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def learner_repo():
    return InMemoryLearnerProfileRepository()


@pytest.fixture
def programme_repo():
    return InMemoryUniversityProgrammeRepository()


@pytest.fixture
def application_repo():
    return InMemoryApplicationRepository()


@pytest.fixture
def scoring_rule_repo():
    return InMemoryScoringRuleRepository()


@pytest.fixture
def learner_svc(learner_repo, application_repo):
    return LearnerProfileService(learner_repo=learner_repo, application_repo=application_repo)


@pytest.fixture
def learner_svc_with_rules(learner_repo, application_repo, scoring_rule_repo):
    """LearnerProfileService wired with a ScoringRuleRepository for REQ-002 tests."""
    return LearnerProfileService(
        learner_repo=learner_repo,
        application_repo=application_repo,
        scoring_rule_repo=scoring_rule_repo,
    )


@pytest.fixture
def programme_svc(programme_repo):
    return UniversityProgrammeService(programme_repo=programme_repo)


@pytest.fixture
def application_svc(application_repo, learner_repo, programme_repo):
    return ApplicationService(
        application_repo=application_repo,
        learner_repo=learner_repo,
        programme_repo=programme_repo,
    )


@pytest.fixture
def application_svc_with_rules(application_repo, learner_repo, programme_repo, scoring_rule_repo):
    """ApplicationService wired with a ScoringRuleRepository for REQ-002 tests."""
    return ApplicationService(
        application_repo=application_repo,
        learner_repo=learner_repo,
        programme_repo=programme_repo,
        scoring_rule_repo=scoring_rule_repo,
    )


def _make_learner() -> LearnerProfile:
    return LearnerProfile(
        learner_id=uuid4(),
        full_name="Thabo Nkosi",
        school_id_number="SCH-001",
        grade=12,
        status=ProfileStatusEnum.Incomplete,
        counselor_id=uuid4(),
        school_id=uuid4(),
    )


def _make_programme(deadline: date = date(2099, 12, 31), aps: int = 28) -> UniversityProgramme:
    return UniversityProgramme(
        programme_id=uuid4(),
        university_id=uuid4(),
        name="BSc Computer Science",
        faculty="Science",
        minimum_aps=aps,
        application_deadline=deadline,
        application_fee=Decimal("200.00"),
        required_documents=["ID", "Matric Certificate"],
        status=ProgrammeStatusEnum.Draft,
        published_by=uuid4(),
    )


def _make_mark(learner_id, score: int = 75) -> Mark:
    return Mark(
        mark_id=uuid4(),
        learner_id=learner_id,
        subject_name="Mathematics",
        score=score,
        exam_type="NSC",
        academic_year=2024,
    )


def _make_named_mark(subject_name: str, score: int) -> Mark:
    """Create a mark for a specific subject — used in REQ-003 subject-requirement tests."""
    return Mark(
        mark_id=uuid4(),
        learner_id=uuid4(),
        subject_name=subject_name,
        score=score,
        exam_type="NSC",
        academic_year=2025,
    )


_GENERIC_SUBJECTS = [
    "Mathematics", "English", "Life Sciences",
    "Physical Sciences", "History", "Geography",
]


def _add_marks_to_learner(learner: LearnerProfile, score: int = 90, subjects: list[str] | None = None) -> None:
    """Append marks directly to a learner's marks list (for eligibility setup)."""
    for subj in (subjects or _GENERIC_SUBJECTS):
        learner.marks.append(Mark(
            mark_id=uuid4(),
            learner_id=learner.learner_id,
            subject_name=subj,
            score=score,
            exam_type="NSC",
            academic_year=2024,
        ))


def _make_programme_with_subjects(
    required_subjects: dict[str, int],
    deadline: date = date(2099, 12, 31),
    aps: int = 28,
) -> UniversityProgramme:
    """Create a synthetic programme with compulsory subject requirements (REQ-003)."""
    return UniversityProgramme(
        programme_id=uuid4(),
        university_id=uuid4(),
        name="BSc Computer Science",
        faculty="Science",
        minimum_aps=aps,
        application_deadline=deadline,
        application_fee=Decimal("200.00"),
        required_documents=["ID", "Matric Certificate"],
        status=ProgrammeStatusEnum.Draft,
        published_by=uuid4(),
        required_subjects=required_subjects,
    )


# ─────────────────────────────────────────────────────────────────────────────
# LearnerProfileService tests
# ─────────────────────────────────────────────────────────────────────────────

class TestLearnerProfileService:

    def test_create_and_get_profile(self, learner_svc):
        learner = _make_learner()
        learner_svc.create_profile(learner)
        retrieved = learner_svc.get_profile(learner.learner_id)
        assert retrieved.learner_id == learner.learner_id
        assert retrieved.full_name == "Thabo Nkosi"

    def test_get_nonexistent_profile_raises(self, learner_svc):
        with pytest.raises(LearnerNotFoundError):
            learner_svc.get_profile(uuid4())

    def test_list_profiles(self, learner_svc):
        learner_svc.create_profile(_make_learner())
        learner_svc.create_profile(_make_learner())
        assert len(learner_svc.list_profiles()) == 2

    def test_update_profile(self, learner_svc):
        learner = _make_learner()
        learner_svc.create_profile(learner)
        updated = learner_svc.update_profile(learner.learner_id, full_name="Sipho Dlamini")
        assert updated.full_name == "Sipho Dlamini"

    def test_update_nonexistent_profile_raises(self, learner_svc):
        with pytest.raises(LearnerNotFoundError):
            learner_svc.update_profile(uuid4(), full_name="Ghost")

    def test_delete_profile(self, learner_svc):
        learner = _make_learner()
        learner_svc.create_profile(learner)
        learner_svc.delete_profile(learner.learner_id)
        with pytest.raises(LearnerNotFoundError):
            learner_svc.get_profile(learner.learner_id)

    def test_add_valid_mark(self, learner_svc):
        learner = _make_learner()
        learner_svc.create_profile(learner)
        mark = _make_mark(learner.learner_id, score=80)
        result = learner_svc.add_mark(learner.learner_id, mark)
        assert len(result.marks) == 1
        profile = learner_svc.get_profile(learner.learner_id)
        assert len(profile.marks) == 1

    def test_add_invalid_mark_raises(self, learner_svc):
        learner = _make_learner()
        learner_svc.create_profile(learner)
        bad_mark = _make_mark(learner.learner_id, score=150)
        with pytest.raises(ValueError):
            learner_svc.add_mark(learner.learner_id, bad_mark)

    def test_aps_score_top_6(self, learner_svc):
        """APS uses NSC point table and takes top six subjects."""
        learner = _make_learner()
        learner_svc.create_profile(learner)
        # 90,80→7 pts each; 70→6; 60→5; 50→4; 40→3; 30→2 → top 6 = 7+7+6+5+4+3 = 32
        for score in [90, 80, 70, 60, 50, 40, 30]:
            learner_svc.add_mark(learner.learner_id, _make_mark(learner.learner_id, score=score))
        assert learner_svc.get_aps_score(learner.learner_id) == 32

    def test_aps_fewer_than_6_subjects(self, learner_svc):
        """With fewer than six marks, all are summed (score 80 → 7 APS points each)."""
        learner = _make_learner()
        learner_svc.create_profile(learner)
        learner_svc.add_mark(learner.learner_id, _make_mark(learner.learner_id, score=80))
        learner_svc.add_mark(learner.learner_id, _make_mark(learner.learner_id, score=80))
        assert learner_svc.get_aps_score(learner.learner_id) == 14

    def test_deactivate_cancels_active_applications(self, learner_svc, application_repo, programme_repo):
        learner = _make_learner()
        learner_svc.create_profile(learner)

        prog = _make_programme()
        prog.status = ProgrammeStatusEnum.Published
        programme_repo.save(prog)

        app = Application(
            application_id=uuid4(),
            learner_id=learner.learner_id,
            programme_id=prog.programme_id,
            status=ApplicationStatusEnum.Draft,
            payment_reference="",
            fee_amount=Decimal("200"),
            submission_timestamp=None,
            acknowledgement_reference="",
        )
        application_repo.save(app)

        learner_svc.deactivate_profile(learner.learner_id)
        cancelled_app = application_repo.find_by_id(app.application_id)
        assert cancelled_app.status == ApplicationStatusEnum.Cancelled

    def test_deactivate_records_system_cancellation_in_history(self, learner_svc, application_repo, programme_repo):
        """System-initiated cancellation (profile deactivation) must record a StatusHistoryEntry
        with the system actor UUID, not the learner's UUID."""
        from unimatch.services import _SYSTEM_ACTOR_ID

        learner = _make_learner()
        learner_svc.create_profile(learner)

        prog = _make_programme()
        prog.status = ProgrammeStatusEnum.Published
        programme_repo.save(prog)

        app = Application(
            application_id=uuid4(),
            learner_id=learner.learner_id,
            programme_id=prog.programme_id,
            status=ApplicationStatusEnum.Draft,
            payment_reference="",
            fee_amount=Decimal("200"),
            submission_timestamp=None,
            acknowledgement_reference="",
        )
        application_repo.save(app)

        learner_svc.deactivate_profile(learner.learner_id)

        persisted = application_repo.find_by_id(app.application_id)
        history = persisted.get_status_history()
        assert len(history) == 1
        assert history[0].new_status == ApplicationStatusEnum.Cancelled
        assert history[0].changed_by == _SYSTEM_ACTOR_ID
        assert "deactivated" in history[0].note.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Per-university APS scoring tests (REQ-002)
# ─────────────────────────────────────────────────────────────────────────────
#
# All ScoringRule instances below are SYNTHETIC test rules used to verify the
# scoring mechanism. They do NOT represent official admission rules of any
# South African university (Wits, UCT, CPUT or otherwise).

class TestScoringRule:

    def test_default_formula_unchanged(self, learner_svc_with_rules, learner_repo):
        """No university_id → behaviour identical to the standard NSC formula."""
        learner = _make_learner()
        learner_repo.save(learner)
        for score in [80, 70, 60, 50, 40, 30]:  # 7+6+5+4+3+2 = 27
            learner_svc_with_rules.add_mark(learner.learner_id, _make_mark(learner.learner_id, score=score))

        aps_no_uid = learner_svc_with_rules.get_aps_score(learner.learner_id)
        aps_none = learner_svc_with_rules.get_aps_score(learner.learner_id, university_id=None)
        assert aps_no_uid == 27
        assert aps_none == 27

    def test_excluded_subjects(self, learner_svc_with_rules, learner_repo, scoring_rule_repo):
        """Subjects in excluded_subjects must not contribute to APS.

        Synthetic rule: excludes 'Life Orientation', top-6, standard bands.
        Learner has Maths 80 (→7), English 70 (→6), Life Orientation 50 (→4).
        Without exclusion: 7+6+4 = 17. With LO excluded: 7+6 = 13.
        """
        uni_id = uuid4()
        synthetic_rule = ScoringRule(
            university_id=uni_id,
            band_thresholds=NSC_DEFAULT_SCORING_RULE.band_thresholds,
            subject_count=6,
            excluded_subjects=["Life Orientation"],
            subject_weightings={},
        )
        scoring_rule_repo.save(synthetic_rule)

        learner = _make_learner()
        learner_repo.save(learner)
        for subj, score in [("Mathematics", 80), ("English", 70), ("Life Orientation", 50)]:
            learner_svc_with_rules.add_mark(learner.learner_id, Mark(
                mark_id=uuid4(), learner_id=learner.learner_id,
                subject_name=subj, score=score, exam_type="NSC", academic_year=2025,
            ))

        aps_with_rule = learner_svc_with_rules.get_aps_score(learner.learner_id, university_id=uni_id)
        aps_default = learner_svc_with_rules.get_aps_score(learner.learner_id)

        assert aps_default == 17, "Default formula should include LO"
        assert aps_with_rule == 13, "University rule should exclude LO"

    def test_subject_weighting(self, learner_svc_with_rules, learner_repo, scoring_rule_repo):
        """Subject weightings must scale the point contribution before summing.

        Synthetic rule: Maths weighted 2.0, no exclusions, top-6, standard bands.
        Learner has Maths 80 (7 pts × 2.0 = 14.0), English 70 (6 pts × 1.0 = 6.0),
        Life Science 60 (5 pts × 1.0 = 5.0).
        With weighting: floor(14.0 + 6.0 + 5.0) = 25.
        Without weighting: 7 + 6 + 5 = 18.
        """
        uni_id = uuid4()
        synthetic_rule = ScoringRule(
            university_id=uni_id,
            band_thresholds=NSC_DEFAULT_SCORING_RULE.band_thresholds,
            subject_count=6,
            excluded_subjects=[],
            subject_weightings={"Mathematics": 2.0},
        )
        scoring_rule_repo.save(synthetic_rule)

        learner = _make_learner()
        learner_repo.save(learner)
        for subj, score in [("Mathematics", 80), ("English", 70), ("Life Science", 60)]:
            learner_svc_with_rules.add_mark(learner.learner_id, Mark(
                mark_id=uuid4(), learner_id=learner.learner_id,
                subject_name=subj, score=score, exam_type="NSC", academic_year=2025,
            ))

        aps_with_rule = learner_svc_with_rules.get_aps_score(learner.learner_id, university_id=uni_id)
        aps_default = learner_svc_with_rules.get_aps_score(learner.learner_id)

        assert aps_default == 18, "Default formula should not apply weighting"
        assert aps_with_rule == 25, "Maths weighting 2.0 should double its contribution"

    def test_different_aps_per_university(self, learner_svc_with_rules, learner_repo, scoring_rule_repo):
        """The same learner must produce different APS values under different rules.

        Two synthetic rules (NOT official Wits/UCT/CPUT rules):
          - University A: standard NSC, top-6. APS = 18.
          - University B: Maths weighted 2.0, LO excluded, top-6. APS = 25.
        """
        uni_a = uuid4()
        uni_b = uuid4()

        rule_a = ScoringRule(
            university_id=uni_a,
            band_thresholds=NSC_DEFAULT_SCORING_RULE.band_thresholds,
            subject_count=6,
            excluded_subjects=[],
            subject_weightings={},
        )
        rule_b = ScoringRule(
            university_id=uni_b,
            band_thresholds=NSC_DEFAULT_SCORING_RULE.band_thresholds,
            subject_count=6,
            excluded_subjects=["Life Orientation"],
            subject_weightings={"Mathematics": 2.0},
        )
        scoring_rule_repo.save(rule_a)
        scoring_rule_repo.save(rule_b)

        learner = _make_learner()
        learner_repo.save(learner)
        for subj, score in [
            ("Mathematics", 80),     # 7 pts
            ("English", 70),          # 6 pts
            ("Life Science", 60),     # 5 pts
            ("Life Orientation", 50), # 4 pts (excluded by rule_b)
        ]:
            learner_svc_with_rules.add_mark(learner.learner_id, Mark(
                mark_id=uuid4(), learner_id=learner.learner_id,
                subject_name=subj, score=score, exam_type="NSC", academic_year=2025,
            ))

        aps_a = learner_svc_with_rules.get_aps_score(learner.learner_id, university_id=uni_a)
        aps_b = learner_svc_with_rules.get_aps_score(learner.learner_id, university_id=uni_b)
        aps_default = learner_svc_with_rules.get_aps_score(learner.learner_id)

        # Rule A: 7+6+5+4 = 22 (same as default)
        assert aps_a == 22
        assert aps_default == 22
        # Rule B: Maths 7×2=14, English 6, Life Science 5; LO excluded → floor(14+6+5) = 25
        assert aps_b == 25
        assert aps_b != aps_a, "Different rules must produce different APS values"

    def test_no_registered_rule_falls_back_to_default(
        self, learner_svc_with_rules, learner_repo, scoring_rule_repo
    ):
        """Querying with a university_id that has no registered rule must fall back
        to the standard NSC formula rather than raising an error."""
        unregistered_uni = uuid4()

        learner = _make_learner()
        learner_repo.save(learner)
        learner_svc_with_rules.add_mark(learner.learner_id, _make_mark(learner.learner_id, score=80))

        aps_with_unknown = learner_svc_with_rules.get_aps_score(
            learner.learner_id, university_id=unregistered_uni
        )
        aps_default = learner_svc_with_rules.get_aps_score(learner.learner_id)

        assert aps_with_unknown == aps_default == 7


# ─────────────────────────────────────────────────────────────────────────────
# ScoringRule validation tests
# ─────────────────────────────────────────────────────────────────────────────

class TestScoringRuleValidation:
    """Verify that invalid ScoringRule configurations are rejected at construction.

    All rules here are synthetic and do NOT represent official university rules.
    """

    def _valid_rule(self) -> ScoringRule:
        """Minimal valid synthetic rule used as the passing baseline."""
        return ScoringRule(
            university_id=uuid4(),
            band_thresholds=[(80, 7), (70, 6)],
            subject_count=2,
            excluded_subjects=[],
            subject_weightings={},
        )

    # ── subject_count ─────────────────────────────────────────────────────────

    def test_subject_count_zero_raises(self):
        with pytest.raises(ValueError, match="subject_count"):
            ScoringRule(uuid4(), [(80, 7)], 0, [], {})

    def test_subject_count_negative_raises(self):
        with pytest.raises(ValueError, match="subject_count"):
            ScoringRule(uuid4(), [(80, 7)], -1, [], {})

    def test_subject_count_one_is_valid(self):
        rule = ScoringRule(uuid4(), [(80, 7)], 1, [], {})
        assert rule.subject_count == 1

    # ── band_thresholds ───────────────────────────────────────────────────────

    def test_empty_band_thresholds_raises(self):
        with pytest.raises(ValueError, match="band_thresholds"):
            ScoringRule(uuid4(), [], 6, [], {})

    def test_band_threshold_min_score_above_100_raises(self):
        with pytest.raises(ValueError, match="min_score=101"):
            ScoringRule(uuid4(), [(101, 7)], 6, [], {})

    def test_band_threshold_min_score_negative_raises(self):
        with pytest.raises(ValueError, match="min_score=-1"):
            ScoringRule(uuid4(), [(-1, 7)], 6, [], {})

    def test_band_threshold_min_score_zero_is_valid(self):
        """min_score=0 is on the valid NSC boundary and must be accepted."""
        rule = ScoringRule(uuid4(), [(0, 1)], 6, [], {})
        assert len(rule.band_thresholds) == 1

    def test_band_threshold_min_score_100_is_valid(self):
        """min_score=100 is on the valid NSC boundary and must be accepted."""
        rule = ScoringRule(uuid4(), [(100, 7)], 6, [], {})
        assert len(rule.band_thresholds) == 1

    def test_band_threshold_points_zero_raises(self):
        with pytest.raises(ValueError, match="points=0"):
            ScoringRule(uuid4(), [(80, 0)], 6, [], {})

    def test_band_threshold_points_negative_raises(self):
        with pytest.raises(ValueError, match="points=-1"):
            ScoringRule(uuid4(), [(80, -1)], 6, [], {})

    def test_band_threshold_points_one_is_valid(self):
        """points=1 is the NSC minimum and must be accepted."""
        rule = ScoringRule(uuid4(), [(0, 1)], 6, [], {})
        assert rule.band_thresholds[0][1] == 1

    def test_duplicate_min_score_raises(self):
        with pytest.raises(ValueError, match="duplicate min_score=70"):
            ScoringRule(uuid4(), [(70, 6), (70, 7)], 6, [], {})

    def test_non_monotone_points_raises(self):
        """A band awarding fewer points than a lower-score band must be rejected.

        Example: min_score=80 → 1 pt while min_score=70 → 6 pts means a learner
        scoring 82 gets LESS than one scoring 72, which contradicts NSC semantics.
        """
        with pytest.raises(ValueError, match="higher score bands must award at least as many"):
            ScoringRule(uuid4(), [(80, 1), (70, 6)], 6, [], {})

    def test_equal_points_adjacent_bands_are_valid(self):
        """Two adjacent bands with the same points value must be accepted
        (non-strict monotone: = is allowed, only < is rejected)."""
        rule = ScoringRule(uuid4(), [(70, 6), (80, 6)], 6, [], {})
        assert len(rule.band_thresholds) == 2

    def test_standard_nsc_bands_are_valid(self):
        """The six standard NSC bands must construct without error."""
        rule = ScoringRule(
            university_id=uuid4(),
            band_thresholds=[(80, 7), (70, 6), (60, 5), (50, 4), (40, 3), (30, 2)],
            subject_count=6,
            excluded_subjects=[],
            subject_weightings={},
        )
        assert len(rule.band_thresholds) == 6

    # ── subject_weightings ────────────────────────────────────────────────────

    def test_negative_weighting_raises(self):
        with pytest.raises(ValueError, match="Mathematics"):
            ScoringRule(uuid4(), [(80, 7)], 6, [], {"Mathematics": -1.0})

    def test_zero_weighting_raises(self):
        with pytest.raises(ValueError, match="Mathematics"):
            ScoringRule(uuid4(), [(80, 7)], 6, [], {"Mathematics": 0.0})

    def test_infinite_weighting_raises(self):
        with pytest.raises(ValueError, match="Mathematics"):
            ScoringRule(uuid4(), [(80, 7)], 6, [], {"Mathematics": float("inf")})

    def test_negative_infinite_weighting_raises(self):
        with pytest.raises(ValueError, match="Mathematics"):
            ScoringRule(uuid4(), [(80, 7)], 6, [], {"Mathematics": float("-inf")})

    def test_nan_weighting_raises(self):
        with pytest.raises(ValueError, match="Mathematics"):
            ScoringRule(uuid4(), [(80, 7)], 6, [], {"Mathematics": float("nan")})

    def test_weighting_one_is_valid(self):
        """Weighting of 1.0 (identity multiplier) must be accepted."""
        rule = ScoringRule(uuid4(), [(80, 7)], 6, [], {"Mathematics": 1.0})
        assert rule.subject_weightings["Mathematics"] == 1.0

    def test_weighting_fractional_positive_is_valid(self):
        """A weighting below 1.0 but above 0 (e.g. 0.5) must be accepted."""
        rule = ScoringRule(uuid4(), [(80, 7)], 6, [], {"Mathematics": 0.5})
        assert rule.subject_weightings["Mathematics"] == 0.5

    # ── NSC_DEFAULT_SCORING_RULE regression ───────────────────────────────────

    def test_nsc_default_scoring_rule_is_valid(self):
        """The built-in default rule must pass all validation checks."""
        assert NSC_DEFAULT_SCORING_RULE.subject_count == 6
        assert len(NSC_DEFAULT_SCORING_RULE.band_thresholds) == 6
        assert NSC_DEFAULT_SCORING_RULE.subject_weightings == {}

    # ── Combined valid synthetic rule ─────────────────────────────────────────

    def test_valid_synthetic_rule_constructs(self):
        """A fully populated synthetic rule with weighting and exclusions must succeed."""
        rule = self._valid_rule()
        assert rule.subject_count == 2
        assert len(rule.band_thresholds) == 2


# ─────────────────────────────────────────────────────────────────────────────
# Subject-requirement eligibility tests (REQ-003)
# ─────────────────────────────────────────────────────────────────────────────

class TestSubjectRequirements:
    """Tests for the compulsory-subject gate in programme eligibility (REQ-003).

    All learner and programme data are synthetic. Synthetic subject names are
    used throughout; they do not represent official university requirements.
    """

    # ── required_subjects construction validation ─────────────────────────────

    def test_required_subjects_out_of_range_raises(self):
        """A programme with a required minimum mark outside 0-100 must be rejected."""
        with pytest.raises(ValueError, match="Mathematics"):
            _make_programme_with_subjects({"Mathematics": 101})

    def test_required_subjects_negative_raises(self):
        with pytest.raises(ValueError, match="Mathematics"):
            _make_programme_with_subjects({"Mathematics": -1})

    def test_required_subjects_boundary_zero_valid(self):
        p = _make_programme_with_subjects({"Mathematics": 0})
        assert p.required_subjects["Mathematics"] == 0

    def test_required_subjects_boundary_100_valid(self):
        p = _make_programme_with_subjects({"Mathematics": 100})
        assert p.required_subjects["Mathematics"] == 100

    def test_no_required_subjects_valid(self):
        p = _make_programme_with_subjects({})
        assert p.required_subjects == {}

    # ── meets_subject_requirements ────────────────────────────────────────────

    def test_no_requirements_always_passes(self):
        prog = _make_programme_with_subjects({})
        learner = _make_learner()
        assert prog.meets_subject_requirements(learner.marks) is True

    def test_requirement_met_exactly_at_minimum(self):
        """A mark exactly at the minimum threshold must satisfy the requirement."""
        prog = _make_programme_with_subjects({"Mathematics": 60})
        marks = [_make_named_mark("Mathematics", 60)]
        assert prog.meets_subject_requirements(marks) is True

    def test_requirement_met_above_minimum(self):
        prog = _make_programme_with_subjects({"Mathematics": 60})
        marks = [_make_named_mark("Mathematics", 75)]
        assert prog.meets_subject_requirements(marks) is True

    def test_requirement_failed_below_minimum(self):
        prog = _make_programme_with_subjects({"Mathematics": 60})
        marks = [_make_named_mark("Mathematics", 59)]
        assert prog.meets_subject_requirements(marks) is False

    def test_missing_required_subject_fails(self):
        prog = _make_programme_with_subjects({"Mathematics": 60})
        marks = [_make_named_mark("English", 80)]  # no Mathematics mark
        assert prog.meets_subject_requirements(marks) is False

    def test_multiple_marks_best_used(self):
        """When a learner has multiple marks for the same subject, the highest
        score determines whether the requirement is met."""
        prog = _make_programme_with_subjects({"Mathematics": 60})
        # Grade 11 mark below, Grade 12 mark above
        marks = [_make_named_mark("Mathematics", 55), _make_named_mark("Mathematics", 65)]
        assert prog.meets_subject_requirements(marks) is True

    def test_multiple_marks_all_below_fails(self):
        prog = _make_programme_with_subjects({"Mathematics": 60})
        marks = [_make_named_mark("Mathematics", 50), _make_named_mark("Mathematics", 55)]
        assert prog.meets_subject_requirements(marks) is False

    def test_multiple_required_subjects_all_must_pass(self):
        prog = _make_programme_with_subjects({"Mathematics": 60, "English": 50})
        marks = [_make_named_mark("Mathematics", 65), _make_named_mark("English", 55)]
        assert prog.meets_subject_requirements(marks) is True

    def test_multiple_required_subjects_one_fails(self):
        prog = _make_programme_with_subjects({"Mathematics": 60, "English": 50})
        marks = [_make_named_mark("Mathematics", 65), _make_named_mark("English", 45)]
        assert prog.meets_subject_requirements(marks) is False

    # ── check_eligibility with subject requirements ───────────────────────────

    def test_high_aps_but_missing_required_subject_is_not_eligible(
        self, programme_svc, programme_repo
    ):
        """A learner with Guaranteed APS must be Not Eligible when a required
        subject is completely absent from their marks (REQ-003)."""
        prog = _make_programme_with_subjects({"Mathematics": 60}, aps=20)
        prog.status = ProgrammeStatusEnum.Published
        programme_repo.save(prog)
        marks = [_make_named_mark("English", 90)]  # no Mathematics
        elig = programme_svc.check_eligibility(prog.programme_id, learner_aps=35, marks=marks)
        assert elig == EligibilityEnum.NotEligible

    def test_high_aps_but_mark_below_minimum_is_not_eligible(
        self, programme_svc, programme_repo
    ):
        """A learner with Guaranteed APS must be Not Eligible when their best
        Mathematics mark is below the required minimum."""
        prog = _make_programme_with_subjects({"Mathematics": 60}, aps=20)
        programme_repo.save(prog)
        marks = [_make_named_mark("Mathematics", 55)]  # below 60
        elig = programme_svc.check_eligibility(prog.programme_id, learner_aps=35, marks=marks)
        assert elig == EligibilityEnum.NotEligible

    def test_all_requirements_met_gives_aps_classification(
        self, programme_svc, programme_repo
    ):
        """When subject requirements are satisfied, the APS margin determines
        the eligibility category."""
        prog = _make_programme_with_subjects({"Mathematics": 60}, aps=28)
        programme_repo.save(prog)
        marks = [_make_named_mark("Mathematics", 75)]
        # APS=32, minimum=28, diff=4 → Guaranteed
        elig = programme_svc.check_eligibility(prog.programme_id, learner_aps=32, marks=marks)
        assert elig == EligibilityEnum.Guaranteed

    def test_no_marks_provided_skips_subject_check(self, programme_svc, programme_repo):
        """When marks=None the subject gate is skipped; only APS margin is used.
        This preserves backward compatibility for callers that do not yet supply marks."""
        prog = _make_programme_with_subjects({"Mathematics": 60}, aps=20)
        programme_repo.save(prog)
        elig = programme_svc.check_eligibility(prog.programme_id, learner_aps=28, marks=None)
        assert elig == EligibilityEnum.Guaranteed  # diff=8 ≥ 4; subject check skipped

    # ── APS boundary checks (no subject requirements) ─────────────────────────

    def test_eligibility_boundary_guaranteed(self, programme_svc, programme_repo):
        """diff >= 4 must be Guaranteed."""
        prog = _make_programme(aps=20)
        programme_repo.save(prog)
        assert programme_svc.check_eligibility(prog.programme_id, 24) == EligibilityEnum.Guaranteed
        assert programme_svc.check_eligibility(prog.programme_id, 30) == EligibilityEnum.Guaranteed

    def test_eligibility_boundary_likely(self, programme_svc, programme_repo):
        """diff in 1..3 must be Likely."""
        prog = _make_programme(aps=20)
        programme_repo.save(prog)
        assert programme_svc.check_eligibility(prog.programme_id, 21) == EligibilityEnum.Likely
        assert programme_svc.check_eligibility(prog.programme_id, 22) == EligibilityEnum.Likely
        assert programme_svc.check_eligibility(prog.programme_id, 23) == EligibilityEnum.Likely

    def test_eligibility_boundary_borderline(self, programme_svc, programme_repo):
        """diff == 0 (APS exactly at minimum) must be Borderline."""
        prog = _make_programme(aps=20)
        programme_repo.save(prog)
        assert programme_svc.check_eligibility(prog.programme_id, 20) == EligibilityEnum.Borderline

    def test_eligibility_boundary_not_eligible(self, programme_svc, programme_repo):
        """diff < 0 must be Not Eligible."""
        prog = _make_programme(aps=20)
        programme_repo.save(prog)
        assert programme_svc.check_eligibility(prog.programme_id, 19) == EligibilityEnum.NotEligible
        assert programme_svc.check_eligibility(prog.programme_id, 0) == EligibilityEnum.NotEligible

    # ── update_programme validation ───────────────────────────────────────────

    def test_update_programme_invalid_required_subjects_raises(
        self, programme_svc, programme_repo
    ):
        prog = _make_programme()
        programme_repo.save(prog)
        with pytest.raises(ValueError, match="Mathematics"):
            programme_svc.update_programme(prog.programme_id, required_subjects={"Mathematics": 105})

    def test_update_programme_valid_required_subjects(self, programme_svc, programme_repo):
        prog = _make_programme()
        programme_repo.save(prog)
        updated = programme_svc.update_programme(
            prog.programme_id, required_subjects={"Mathematics": 60}
        )
        assert updated.required_subjects == {"Mathematics": 60}


# ─────────────────────────────────────────────────────────────────────────────
# UniversityProgrammeService tests
# ─────────────────────────────────────────────────────────────────────────────

class TestUniversityProgrammeService:

    def test_create_and_get_programme(self, programme_svc):
        prog = _make_programme()
        programme_svc.create_programme(prog)
        retrieved = programme_svc.get_programme(prog.programme_id)
        assert retrieved.name == "BSc Computer Science"

    def test_get_nonexistent_programme_raises(self, programme_svc):
        with pytest.raises(ProgrammeNotFoundError):
            programme_svc.get_programme(uuid4())

    def test_list_programmes(self, programme_svc):
        programme_svc.create_programme(_make_programme())
        programme_svc.create_programme(_make_programme())
        assert len(programme_svc.list_programmes()) == 2

    def test_update_programme(self, programme_svc):
        prog = _make_programme()
        programme_svc.create_programme(prog)
        updated = programme_svc.update_programme(prog.programme_id, name="BSc Data Science")
        assert updated.name == "BSc Data Science"

    def test_delete_programme(self, programme_svc):
        prog = _make_programme()
        programme_svc.create_programme(prog)
        programme_svc.delete_programme(prog.programme_id)
        with pytest.raises(ProgrammeNotFoundError):
            programme_svc.get_programme(prog.programme_id)

    def test_publish_programme(self, programme_svc):
        prog = _make_programme(deadline=date(2099, 12, 31))
        programme_svc.create_programme(prog)
        published = programme_svc.publish_programme(prog.programme_id)
        assert published.status == ProgrammeStatusEnum.Published

    def test_publish_with_past_deadline_raises(self, programme_svc):
        prog = _make_programme(deadline=date(2000, 1, 1))
        programme_svc.create_programme(prog)
        with pytest.raises(ValueError):
            programme_svc.publish_programme(prog.programme_id)

    def test_deactivate_programme(self, programme_svc):
        prog = _make_programme()
        programme_svc.create_programme(prog)
        programme_svc.publish_programme(prog.programme_id)
        result = programme_svc.deactivate_programme(prog.programme_id)
        assert result.status == ProgrammeStatusEnum.Deactivated

    def test_list_published_only(self, programme_svc):
        prog1 = _make_programme()
        prog2 = _make_programme()
        programme_svc.create_programme(prog1)
        programme_svc.create_programme(prog2)
        programme_svc.publish_programme(prog1.programme_id)
        published = programme_svc.list_published_programmes()
        assert len(published) == 1
        assert published[0].programme_id == prog1.programme_id

    def test_eligibility_guaranteed(self, programme_svc):
        prog = _make_programme(aps=20)
        programme_svc.create_programme(prog)
        assert programme_svc.check_eligibility(prog.programme_id, 24) == EligibilityEnum.Guaranteed

    def test_eligibility_likely(self, programme_svc):
        prog = _make_programme(aps=20)
        programme_svc.create_programme(prog)
        assert programme_svc.check_eligibility(prog.programme_id, 22) == EligibilityEnum.Likely

    def test_eligibility_borderline(self, programme_svc):
        prog = _make_programme(aps=20)
        programme_svc.create_programme(prog)
        assert programme_svc.check_eligibility(prog.programme_id, 20) == EligibilityEnum.Borderline

    def test_eligibility_not_eligible(self, programme_svc):
        prog = _make_programme(aps=28)
        programme_svc.create_programme(prog)
        assert programme_svc.check_eligibility(prog.programme_id, 20) == EligibilityEnum.NotEligible

    def test_publish_programme_with_past_deadline_raises(self, programme_svc):
        prog = _make_programme(deadline=date(2000, 1, 1))
        programme_svc.create_programme(prog)
        with pytest.raises(ValueError):
            programme_svc.publish_programme(prog.programme_id)

    def test_deactivate_draft_programme_raises(self, programme_svc):
        """Cannot deactivate a Draft programme — must publish it first."""
        prog = _make_programme()
        programme_svc.create_programme(prog)
        with pytest.raises(ValueError):
            programme_svc.deactivate_programme(prog.programme_id)

    def test_delete_published_programme_raises(self, programme_svc):
        """Published programmes must be deactivated before they can be deleted."""
        prog = _make_programme()
        programme_svc.create_programme(prog)
        programme_svc.publish_programme(prog.programme_id)
        with pytest.raises(ValueError):
            programme_svc.delete_programme(prog.programme_id)

    def test_update_programme_blank_name_raises(self, programme_svc):
        """Updating a programme name to whitespace-only is not allowed."""
        prog = _make_programme()
        programme_svc.create_programme(prog)
        with pytest.raises(ValueError):
            programme_svc.update_programme(prog.programme_id, name="   ")


# ─────────────────────────────────────────────────────────────────────────────
# ApplicationService tests
# ─────────────────────────────────────────────────────────────────────────────

class TestApplicationService:

    def _setup(self, learner_repo, programme_repo):
        """Create and persist a Guaranteed-eligible learner + published programme.

        Learner has 6 subjects each scoring 90 (7 APS pts each → APS 42).
        Programme minimum_aps=28. Diff=14 ≥ 4 → Guaranteed.
        """
        learner = _make_learner()
        _add_marks_to_learner(learner, score=90)
        learner_repo.save(learner)

        prog = _make_programme()
        prog.status = ProgrammeStatusEnum.Published
        programme_repo.save(prog)

        return learner, prog

    def test_create_application_success(self, application_svc, learner_repo, programme_repo):
        learner, prog = self._setup(learner_repo, programme_repo)
        app = application_svc.create_application(
            learner_id=learner.learner_id,
            programme_id=prog.programme_id,
            fee_amount=Decimal("200"),
        )
        assert app.status == ApplicationStatusEnum.Draft
        assert app.learner_id == learner.learner_id

    def test_create_application_learner_not_found(self, application_svc, programme_repo):
        prog = _make_programme()
        prog.status = ProgrammeStatusEnum.Published
        programme_repo.save(prog)
        with pytest.raises(LearnerNotFoundError):
            application_svc.create_application(uuid4(), prog.programme_id, Decimal("200"))

    def test_create_application_programme_not_found(self, application_svc, learner_repo):
        learner = _make_learner()
        learner_repo.save(learner)
        with pytest.raises(ProgrammeNotFoundError):
            application_svc.create_application(learner.learner_id, uuid4(), Decimal("200"))

    def test_create_application_programme_not_active(self, application_svc, learner_repo, programme_repo):
        learner = _make_learner()
        learner_repo.save(learner)
        prog = _make_programme()  # Draft
        programme_repo.save(prog)
        with pytest.raises(ProgrammeNotActiveError):
            application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))

    def test_create_application_expired_programme(self, application_svc, learner_repo, programme_repo):
        learner = _make_learner()
        learner_repo.save(learner)
        prog = _make_programme(deadline=date(2000, 1, 1))
        prog.status = ProgrammeStatusEnum.Published
        programme_repo.save(prog)
        with pytest.raises(ProgrammeNotActiveError):
            application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))

    def test_create_application_duplicate_rejected(self, application_svc, learner_repo, programme_repo):
        learner, prog = self._setup(learner_repo, programme_repo)
        application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))
        with pytest.raises(DuplicateApplicationError):
            application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))

    def test_cancelled_applications_dont_block_new_applications(self, application_svc, learner_repo, programme_repo):
        """Cancelled (terminal) applications do not block a learner from applying again."""
        learner = _make_learner()
        _add_marks_to_learner(learner, score=90)
        learner_repo.save(learner)

        for _ in range(3):
            prog = _make_programme()
            prog.status = ProgrammeStatusEnum.Published
            programme_repo.save(prog)
            app = application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))
            application_svc.cancel_application(app.application_id, uuid4())

        new_prog = _make_programme()
        new_prog.status = ProgrammeStatusEnum.Published
        programme_repo.save(new_prog)
        new_app = application_svc.create_application(learner.learner_id, new_prog.programme_id, Decimal("200"))
        assert new_app.status == ApplicationStatusEnum.Draft

    def test_get_application(self, application_svc, learner_repo, programme_repo):
        learner, prog = self._setup(learner_repo, programme_repo)
        app = application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))
        retrieved = application_svc.get_application(app.application_id)
        assert retrieved.application_id == app.application_id

    def test_get_nonexistent_application_raises(self, application_svc):
        with pytest.raises(ApplicationNotFoundError):
            application_svc.get_application(uuid4())

    def test_list_for_learner(self, application_svc, learner_repo, programme_repo):
        learner = _make_learner()
        _add_marks_to_learner(learner, score=90)
        learner_repo.save(learner)
        for _ in range(3):
            prog = _make_programme()
            prog.status = ProgrammeStatusEnum.Published
            programme_repo.save(prog)
            application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))
        apps = application_svc.list_for_learner(learner.learner_id)
        assert len(apps) == 3

    def test_cancel_application(self, application_svc, learner_repo, programme_repo):
        learner, prog = self._setup(learner_repo, programme_repo)
        app = application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))
        actor = uuid4()
        cancelled = application_svc.cancel_application(app.application_id, actor)
        assert cancelled.status == ApplicationStatusEnum.Cancelled

    def test_cancel_records_status_history_entry(self, application_svc, learner_repo, programme_repo, application_repo):
        """Cancelling an application must append a StatusHistoryEntry to the audit trail."""
        learner, prog = self._setup(learner_repo, programme_repo)
        app = application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))
        actor = uuid4()
        application_svc.cancel_application(app.application_id, actor)

        persisted = application_repo.find_by_id(app.application_id)
        history = persisted.get_status_history()
        assert len(history) == 1
        assert history[0].previous_status == ApplicationStatusEnum.Draft
        assert history[0].new_status == ApplicationStatusEnum.Cancelled
        assert history[0].changed_by == actor

    def test_cancel_accepted_application_raises(self, application_svc, learner_repo, programme_repo, application_repo):
        learner, prog = self._setup(learner_repo, programme_repo)
        app = application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))
        app.status = ApplicationStatusEnum.Accepted
        application_repo.save(app)
        with pytest.raises(InvalidStatusTransitionError):
            application_svc.cancel_application(app.application_id, uuid4())

    def test_delete_application(self, application_svc, learner_repo, programme_repo):
        learner, prog = self._setup(learner_repo, programme_repo)
        app = application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))
        application_svc.delete_application(app.application_id)
        with pytest.raises(ApplicationNotFoundError):
            application_svc.get_application(app.application_id)


# ─────────────────────────────────────────────────────────────────────────────
# Eligibility enforcement at application creation (REQ-004)
# ─────────────────────────────────────────────────────────────────────────────

class TestApplicationServiceEligibilityEnforcement:
    """REQ-004: only Guaranteed and Likely learners may create applications.

    All learner and programme data are synthetic. APS values are constructed
    by choosing mark scores that produce known point values under the standard
    NSC table (score ≥80 → 7pts, ≥70 → 6pts, ≥60 → 5pts, ≥50 → 4pts).
    """

    def _published_prog(self, programme_repo, aps: int = 20, required_subjects: dict | None = None) -> UniversityProgramme:
        if required_subjects:
            prog = _make_programme_with_subjects(required_subjects, aps=aps)
        else:
            prog = _make_programme(aps=aps)
        prog.status = ProgrammeStatusEnum.Published
        programme_repo.save(prog)
        return prog

    def test_guaranteed_learner_application_succeeds(self, application_svc, learner_repo, programme_repo):
        """diff ≥ 4 → Guaranteed → application created."""
        # 4 subjects × 90 score = 4 × 7pts = APS 28; programme min=20; diff=8 ≥ 4
        learner = _make_learner()
        _add_marks_to_learner(learner, score=90, subjects=["Maths", "English", "Science", "History"])
        learner_repo.save(learner)
        prog = self._published_prog(programme_repo, aps=20)

        app = application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))
        assert app.status == ApplicationStatusEnum.Draft

    def test_likely_learner_application_succeeds(self, application_svc, learner_repo, programme_repo):
        """diff in 1..3 → Likely → application created."""
        # 3 subjects × 90 = APS 21; programme min=20; diff=1
        learner = _make_learner()
        _add_marks_to_learner(learner, score=90, subjects=["Maths", "English", "Science"])
        learner_repo.save(learner)
        prog = self._published_prog(programme_repo, aps=20)

        app = application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))
        assert app.status == ApplicationStatusEnum.Draft

    def test_borderline_learner_application_rejected(self, application_svc, learner_repo, programme_repo):
        """diff == 0 → Borderline → NotEligibleError raised."""
        # 4 subjects × 60 score = 4 × 5pts = APS 20; programme min=20; diff=0
        learner = _make_learner()
        _add_marks_to_learner(learner, score=60, subjects=["Maths", "English", "Science", "History"])
        learner_repo.save(learner)
        prog = self._published_prog(programme_repo, aps=20)

        with pytest.raises(NotEligibleError) as exc_info:
            application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))
        assert exc_info.value.eligibility.value == "Borderline"

    def test_not_eligible_learner_application_rejected(self, application_svc, learner_repo, programme_repo):
        """diff < 0 → NotEligible → NotEligibleError raised."""
        # 3 subjects × 50 score = 3 × 4pts = APS 12; programme min=20; diff=-8
        learner = _make_learner()
        _add_marks_to_learner(learner, score=50, subjects=["Maths", "English", "Science"])
        learner_repo.save(learner)
        prog = self._published_prog(programme_repo, aps=20)

        with pytest.raises(NotEligibleError) as exc_info:
            application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))
        assert exc_info.value.eligibility.value == "NotEligible"

    def test_high_aps_but_fails_compulsory_subject_rejected(self, application_svc, learner_repo, programme_repo):
        """A Guaranteed APS but a failing compulsory subject mark → NotEligibleError.

        This verifies that APS alone cannot bypass subject-requirement checking.
        Learner has 6 subjects (none of which is Mathematics) at score 90 → APS 42,
        and a single Mathematics mark at 40 (below the required minimum of 60).
        """
        learner = _make_learner()
        # 6 non-Mathematics subjects × 90 → APS 42, well above programme min 20
        _add_marks_to_learner(
            learner, score=90,
            subjects=["English", "Life Sciences", "Physical Sciences", "History", "Geography", "Arts"],
        )
        # Mathematics mark exists but is below the required minimum of 60
        learner.marks.append(Mark(
            mark_id=uuid4(), learner_id=learner.learner_id,
            subject_name="Mathematics", score=40, exam_type="NSC", academic_year=2024,
        ))
        learner_repo.save(learner)
        prog = self._published_prog(programme_repo, aps=20, required_subjects={"Mathematics": 60})

        with pytest.raises(NotEligibleError) as exc_info:
            application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))
        assert exc_info.value.eligibility.value == "NotEligible"

    def test_missing_required_subject_rejected(self, application_svc, learner_repo, programme_repo):
        """Learner without any mark for a required subject is rejected regardless of APS."""
        learner = _make_learner()
        # Learner has no Mathematics marks at all
        _add_marks_to_learner(learner, score=90, subjects=["English", "Science", "History", "Geography"])
        learner_repo.save(learner)
        prog = self._published_prog(programme_repo, aps=20, required_subjects={"Mathematics": 50})

        with pytest.raises(NotEligibleError):
            application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))

    def test_more_than_five_simultaneous_applications_allowed(self, application_svc, learner_repo, programme_repo):
        """Removing the cap means a learner may hold more than 5 active applications."""
        learner = _make_learner()
        _add_marks_to_learner(learner, score=90)
        learner_repo.save(learner)

        created = []
        for _ in range(7):
            prog = _make_programme()
            prog.status = ProgrammeStatusEnum.Published
            programme_repo.save(prog)
            app = application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))
            created.append(app)

        assert len(created) == 7
        assert all(a.status == ApplicationStatusEnum.Draft for a in created)

    def test_rejected_application_not_persisted(self, application_svc, learner_repo, programme_repo, application_repo):
        """An ineligible application must not leave a record in the repository."""
        learner = _make_learner()
        # No marks → APS 0, fails any programme with min > 0
        learner_repo.save(learner)
        prog = self._published_prog(programme_repo, aps=20)

        with pytest.raises(NotEligibleError):
            application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))

        assert application_repo.find_all() == []

    def test_duplicate_rejected_after_eligible_first_application(self, application_svc, learner_repo, programme_repo):
        """DuplicateApplicationError is raised when an eligible learner re-applies
        to the same programme they already have an active application for."""
        learner = _make_learner()
        _add_marks_to_learner(learner, score=90)
        learner_repo.save(learner)
        prog = self._published_prog(programme_repo, aps=20)

        application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))
        with pytest.raises(DuplicateApplicationError):
            application_svc.create_application(learner.learner_id, prog.programme_id, Decimal("200"))


# ─────────────────────────────────────────────────────────────────────────────
# Per-university APS scoring at application creation (REQ-002)
# ─────────────────────────────────────────────────────────────────────────────

class TestApplicationServiceREQ002:
    """REQ-002: create_application must use the university-specific APS formula
    when a ScoringRule is registered for the target programme's university.

    All ScoringRule instances are SYNTHETIC test rules. They do not represent
    the official scoring formula of any South African university.

    APS point values used in comments follow the standard NSC table:
      score ≥80 → 7 pts, ≥70 → 6 pts, ≥60 → 5 pts, ≥50 → 4 pts.
    """

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _synthetic_rule(self, university_id: UUID, **overrides) -> ScoringRule:
        """Return a synthetic ScoringRule with standard NSC bands and top-6 count.

        Keyword overrides are merged into the defaults so individual tests can
        customise excluded_subjects, subject_weightings, etc.
        """
        defaults: dict = dict(
            university_id=university_id,
            band_thresholds=NSC_DEFAULT_SCORING_RULE.band_thresholds,
            subject_count=6,
            excluded_subjects=[],
            subject_weightings={},
        )
        defaults.update(overrides)
        return ScoringRule(**defaults)

    def _make_and_save_learner(self, learner_repo, marks: dict) -> LearnerProfile:
        """Create a learner, attach the given subject marks, and save to repo."""
        learner = _make_learner()
        for subject, score in marks.items():
            learner.marks.append(Mark(
                mark_id=uuid4(),
                learner_id=learner.learner_id,
                subject_name=subject,
                score=score,
                exam_type="NSC",
                academic_year=2025,
            ))
        learner_repo.save(learner)
        return learner

    def _published_programme_for_university(
        self,
        programme_repo,
        university_id: UUID,
        min_aps: int,
        required_subjects: dict | None = None,
    ) -> UniversityProgramme:
        """Create and save a Published programme owned by the given university."""
        prog = UniversityProgramme(
            programme_id=uuid4(),
            university_id=university_id,
            name="BSc Engineering",
            faculty="Engineering",
            minimum_aps=min_aps,
            application_deadline=date(2099, 12, 31),
            application_fee=Decimal("300.00"),
            required_documents=["ID"],
            status=ProgrammeStatusEnum.Published,
            published_by=uuid4(),
            required_subjects=required_subjects or {},
        )
        programme_repo.save(prog)
        return prog

    # ── Tests ─────────────────────────────────────────────────────────────────

    def test_university_rule_blocks_application_when_nsc_aps_passes(
        self, application_svc_with_rules, learner_repo, programme_repo, scoring_rule_repo
    ):
        """University-specific APS falls below minimum where NSC APS would pass.

        Learner marks (synthetic):
          Mathematics=90 → 7pts, English=70 → 6pts, Life Orientation=50 → 4pts
          NSC APS (top-6, all subjects) = 7+6+4 = 17

        Synthetic rule: excludes Mathematics.
          University APS = 6+4 = 10 (English and LO only)

        Programme min_aps=12:
          NSC:  diff = 17-12 = 5 → Guaranteed → would allow
          Rule: diff = 10-12 = -2 → NotEligible → must block
        """
        uni_id = uuid4()
        scoring_rule_repo.save(
            self._synthetic_rule(uni_id, excluded_subjects=["Mathematics"])
        )
        learner = self._make_and_save_learner(
            learner_repo,
            {"Mathematics": 90, "English": 70, "Life Orientation": 50},
        )
        prog = self._published_programme_for_university(programme_repo, uni_id, min_aps=12)

        with pytest.raises(NotEligibleError) as exc_info:
            application_svc_with_rules.create_application(
                learner.learner_id, prog.programme_id, Decimal("300")
            )
        assert exc_info.value.eligibility == EligibilityEnum.NotEligible

    def test_university_rule_allows_application_when_nsc_aps_fails(
        self, application_svc_with_rules, learner_repo, programme_repo, scoring_rule_repo
    ):
        """University-specific APS passes where NSC APS would not.

        Learner marks (synthetic):
          Mathematics=80 → 7pts, English=70 → 6pts
          NSC APS = 7+6 = 13

        Synthetic rule: Mathematics weighted 2.0.
          University APS = floor(7×2.0 + 6) = floor(20) = 20

        Programme min_aps=15:
          NSC:  diff = 13-15 = -2 → NotEligible → would block
          Rule: diff = 20-15 = 5  → Guaranteed → must allow
        """
        uni_id = uuid4()
        scoring_rule_repo.save(
            self._synthetic_rule(uni_id, subject_weightings={"Mathematics": 2.0})
        )
        learner = self._make_and_save_learner(
            learner_repo,
            {"Mathematics": 80, "English": 70},
        )
        prog = self._published_programme_for_university(programme_repo, uni_id, min_aps=15)

        app = application_svc_with_rules.create_application(
            learner.learner_id, prog.programme_id, Decimal("300")
        )
        assert app.status == ApplicationStatusEnum.Draft

    def test_fallback_to_nsc_when_no_rule_registered(
        self, application_svc_with_rules, learner_repo, programme_repo
    ):
        """When the programme's university has no registered ScoringRule, the
        standard NSC formula is used and the application proceeds normally.

        Learner marks: Mathematics=90, English=90, Science=90 → NSC APS = 3×7 = 21.
        Programme min_aps=20; diff=1 → Likely → allowed.
        """
        uni_id = uuid4()  # no rule saved for this university
        learner = self._make_and_save_learner(
            learner_repo,
            {"Mathematics": 90, "English": 90, "Science": 90},
        )
        prog = self._published_programme_for_university(programme_repo, uni_id, min_aps=20)

        app = application_svc_with_rules.create_application(
            learner.learner_id, prog.programme_id, Decimal("300")
        )
        assert app.status == ApplicationStatusEnum.Draft

    def test_exact_minimum_with_university_rule_is_borderline_and_blocked(
        self, application_svc_with_rules, learner_repo, programme_repo, scoring_rule_repo
    ):
        """University-specific APS exactly equals the programme minimum (diff=0 → Borderline).

        Learner marks: Mathematics=80 → 7pts, English=70 → 6pts.
        Synthetic rule (Maths weighted 2.0): APS = floor(14+6) = 20.
        Programme min_aps=20 → diff=0 → Borderline → NotEligibleError.
        """
        uni_id = uuid4()
        scoring_rule_repo.save(
            self._synthetic_rule(uni_id, subject_weightings={"Mathematics": 2.0})
        )
        learner = self._make_and_save_learner(
            learner_repo,
            {"Mathematics": 80, "English": 70},
        )
        prog = self._published_programme_for_university(programme_repo, uni_id, min_aps=20)

        with pytest.raises(NotEligibleError) as exc_info:
            application_svc_with_rules.create_application(
                learner.learner_id, prog.programme_id, Decimal("300")
            )
        assert exc_info.value.eligibility == EligibilityEnum.Borderline

    def test_one_above_minimum_with_university_rule_is_likely_and_allowed(
        self, application_svc_with_rules, learner_repo, programme_repo, scoring_rule_repo
    ):
        """University-specific APS is exactly 1 above minimum (diff=1 → Likely → allowed).

        Learner marks: Mathematics=80 → 7pts, English=70 → 6pts.
        Synthetic rule (Maths weighted 2.0): APS = floor(14+6) = 20.
        Programme min_aps=19 → diff=1 → Likely → application created.
        """
        uni_id = uuid4()
        scoring_rule_repo.save(
            self._synthetic_rule(uni_id, subject_weightings={"Mathematics": 2.0})
        )
        learner = self._make_and_save_learner(
            learner_repo,
            {"Mathematics": 80, "English": 70},
        )
        prog = self._published_programme_for_university(programme_repo, uni_id, min_aps=19)

        app = application_svc_with_rules.create_application(
            learner.learner_id, prog.programme_id, Decimal("300")
        )
        assert app.status == ApplicationStatusEnum.Draft

    def test_university_rule_with_failed_compulsory_subject_rejects_and_does_not_persist(
        self,
        application_svc_with_rules,
        learner_repo,
        programme_repo,
        application_repo,
        scoring_rule_repo,
    ):
        """A compulsory-subject failure rejects the application before the APS
        calculation is reached, even when a university-specific rule is registered.

        Learner marks: Mathematics=80, English=70.
          Synthetic rule (Maths weighted 2.0):
            University APS = floor(7×2.0 + 6) = 20 → would give Guaranteed if reached.
          Programme requires Mathematics ≥ 90; learner's best Mathematics mark is 80 → FAIL.

        Expected: NotEligibleError raised; no application record persisted.
        """
        uni_id = uuid4()
        scoring_rule_repo.save(
            self._synthetic_rule(uni_id, subject_weightings={"Mathematics": 2.0})
        )
        learner = self._make_and_save_learner(
            learner_repo,
            {"Mathematics": 80, "English": 70},
        )
        prog = self._published_programme_for_university(
            programme_repo, uni_id, min_aps=15,
            required_subjects={"Mathematics": 90},  # learner has 80, below 90
        )

        with pytest.raises(NotEligibleError) as exc_info:
            application_svc_with_rules.create_application(
                learner.learner_id, prog.programme_id, Decimal("300")
            )
        assert exc_info.value.eligibility == EligibilityEnum.NotEligible
        assert application_repo.find_all() == []

    def test_university_rule_with_satisfied_compulsory_subject_uses_university_aps(
        self,
        application_svc_with_rules,
        learner_repo,
        programme_repo,
        scoring_rule_repo,
    ):
        """When compulsory subjects are satisfied, the university-specific APS
        governs the eligibility decision.

        Learner marks: Mathematics=80 → 7pts, English=70 → 6pts.
          NSC APS = 7+6 = 13.
          Synthetic rule (Maths weighted 2.0): University APS = floor(14+6) = 20.
          Programme requires Mathematics ≥ 60; learner's Mathematics is 80 → PASS.
          Programme min_aps=15:
            NSC:  diff = 13-15 = -2 → NotEligible → would block
            Rule: diff = 20-15 = 5  → Guaranteed → must allow

        Expected: application created, confirming university APS is used after
        compulsory subjects pass.
        """
        uni_id = uuid4()
        scoring_rule_repo.save(
            self._synthetic_rule(uni_id, subject_weightings={"Mathematics": 2.0})
        )
        learner = self._make_and_save_learner(
            learner_repo,
            {"Mathematics": 80, "English": 70},
        )
        prog = self._published_programme_for_university(
            programme_repo, uni_id, min_aps=15,
            required_subjects={"Mathematics": 60},  # learner has 80, satisfies ≥60
        )

        app = application_svc_with_rules.create_application(
            learner.learner_id, prog.programme_id, Decimal("300")
        )
        assert app.status == ApplicationStatusEnum.Draft
