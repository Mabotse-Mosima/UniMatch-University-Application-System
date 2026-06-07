"""
api/__init__.py
===============
FastAPI REST API for UniMatch (Assignment 12).

Exposes three resource groups:
  /api/learners      – LearnerProfile CRUD + APS + deactivation
  /api/programmes    – UniversityProgramme CRUD + publish/deactivate
  /api/applications  – Application lifecycle (create, status update, submit, cancel)

OpenAPI docs are auto-generated at /docs (Swagger UI) and /redoc.

Pydantic request/response models are defined at **module level** so FastAPI
correctly binds JSON bodies (nested classes inside ``create_app()`` are not
reliable for body parsing).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import date
from decimal import Decimal
from typing import List, Optional
from uuid import UUID, uuid4

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from entities import Application, LearnerProfile, Mark, UniversityProgramme
from enums import ApplicationStatusEnum, ProfileStatusEnum, ProgrammeStatusEnum
from repositories_inmemory import (
    InMemoryApplicationRepository,
    InMemoryLearnerProfileRepository,
    InMemoryUniversityProgrammeRepository,
)
from services import (
    ApplicationNotFoundError,
    ApplicationService,
    DuplicateApplicationError,
    InvalidStatusTransitionError,
    LearnerNotFoundError,
    LearnerProfileService,
    ProgrammeNotActiveError,
    ProgrammeNotFoundError,
    TooManyActiveApplicationsError,
    UniversityProgrammeService,
)

# ────────────────────────────────────────────────────────────────────────────
# Logging configuration
# ────────────────────────────────────────────────────────────────────────────
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("unimatch.api")

# ─────────────────────────────────────────────────────────────────────────────
# Pydantic schemas (module level — required for correct JSON body binding)
# ─────────────────────────────────────────────────────────────────────────────


class CreateLearnerRequest(BaseModel):
    full_name: str = Field(..., json_schema_extra={"example": "Thabo Nkosi"})
    school_id_number: str = Field(..., json_schema_extra={"example": "2024-0001"})
    grade: int = Field(..., ge=8, le=12, json_schema_extra={"example": 12})
    counselor_id: UUID = Field(..., json_schema_extra={"example": "00000000-0000-0000-0000-000000000001"})
    school_id: UUID = Field(..., json_schema_extra={"example": "00000000-0000-0000-0000-000000000002"})


class UpdateLearnerRequest(BaseModel):
    full_name: Optional[str] = None
    grade: Optional[int] = Field(None, ge=8, le=12)
    school_id_number: Optional[str] = None


class AddMarkRequest(BaseModel):
    subject_name: str = Field(..., json_schema_extra={"example": "Mathematics"})
    score: int = Field(..., ge=0, le=100, json_schema_extra={"example": 75})
    exam_type: str = Field(..., json_schema_extra={"example": "NSC"})
    academic_year: int = Field(..., json_schema_extra={"example": 2024})


class LearnerResponse(BaseModel):
    learner_id: UUID
    full_name: str
    school_id_number: str
    grade: int
    status: str
    counselor_id: UUID
    school_id: UUID
    aps_score: int
    mark_count: int


class ApsResponse(BaseModel):
    learner_id: UUID
    aps_score: int


class CreateProgrammeRequest(BaseModel):
    university_id: UUID = Field(..., json_schema_extra={"example": "00000000-0000-0000-0000-000000000010"})
    name: str = Field(..., json_schema_extra={"example": "BSc Computer Science"})
    faculty: str = Field(..., json_schema_extra={"example": "Science"})
    minimum_aps: int = Field(..., ge=0, le=42, json_schema_extra={"example": 28})
    application_deadline: date = Field(..., json_schema_extra={"example": "2025-09-30"})
    application_fee: Decimal = Field(..., json_schema_extra={"example": "200.00"})
    required_documents: List[str] = Field(default_factory=list)
    published_by: UUID = Field(..., json_schema_extra={"example": "00000000-0000-0000-0000-000000000020"})


class UpdateProgrammeRequest(BaseModel):
    name: Optional[str] = None
    faculty: Optional[str] = None
    minimum_aps: Optional[int] = Field(None, ge=0, le=42)
    application_fee: Optional[Decimal] = None
    required_documents: Optional[List[str]] = None


class ExtendDeadlineRequest(BaseModel):
    new_deadline: date = Field(..., json_schema_extra={"example": "2025-10-31"})


class ProgrammeResponse(BaseModel):
    programme_id: UUID
    university_id: UUID
    name: str
    faculty: str
    minimum_aps: int
    application_deadline: date
    application_fee: str
    status: str
    is_active: bool


class EligibilityResponse(BaseModel):
    programme_id: UUID
    learner_aps: int
    minimum_aps: int
    eligibility: str


class CreateApplicationRequest(BaseModel):
    learner_id: UUID = Field(..., json_schema_extra={"example": "00000000-0000-0000-0000-000000000030"})
    programme_id: UUID = Field(..., json_schema_extra={"example": "00000000-0000-0000-0000-000000000040"})
    fee_amount: Decimal = Field(..., json_schema_extra={"example": "200.00"})


class UpdateStatusRequest(BaseModel):
    new_status: ApplicationStatusEnum
    actor_id: UUID = Field(..., json_schema_extra={"example": "00000000-0000-0000-0000-000000000050"})
    note: str = Field(default="", json_schema_extra={"example": "Documents verified"})


class ApplicationResponse(BaseModel):
    application_id: UUID
    learner_id: UUID
    programme_id: UUID
    status: str
    fee_amount: str
    submission_timestamp: Optional[str]
    acknowledgement_reference: str


def _learner_out(p: LearnerProfile) -> LearnerResponse:
    return LearnerResponse(
        learner_id=p.learner_id,
        full_name=p.full_name,
        school_id_number=p.school_id_number,
        grade=p.grade,
        status=p.status.value,
        counselor_id=p.counselor_id,
        school_id=p.school_id,
        aps_score=p.get_aps_score(),
        mark_count=len(p.marks),
    )


def _programme_out(p: UniversityProgramme) -> ProgrammeResponse:
    return ProgrammeResponse(
        programme_id=p.programme_id,
        university_id=p.university_id,
        name=p.name,
        faculty=p.faculty,
        minimum_aps=p.minimum_aps,
        application_deadline=p.application_deadline,
        application_fee=str(p.application_fee),
        status=p.status.value,
        is_active=p.is_active(),
    )


def _application_out(entity: Application) -> ApplicationResponse:
    return ApplicationResponse(
        application_id=entity.application_id,
        learner_id=entity.learner_id,
        programme_id=entity.programme_id,
        status=entity.status.value,
        fee_amount=str(entity.fee_amount),
        submission_timestamp=(
            entity.submission_timestamp.isoformat() if entity.submission_timestamp else None
        ),
        acknowledgement_reference=entity.acknowledgement_reference,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Application factory
# ─────────────────────────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    fastapi_app = FastAPI(
        title="UniMatch API",
        description=(
            "REST API for the UniMatch university application matching system. "
            "Manages learner profiles, university programmes, and application workflows."
        ),
        version="1.0.0",
        contact={"name": "UniMatch Team"},
        license_info={"name": "MIT"},
    )

    # ────────────────────────────────────────────────────────────────────
    # Request logging middleware
    # Logs every endpoint call (INFO), 404 responses (WARNING),
    # and unexpected exceptions (ERROR).
    # ────────────────────────────────────────────────────────────────────
    @fastapi_app.middleware("http")
    async def log_requests(request, call_next):
        logger.info("%s %s called", request.method, request.url.path)
        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error(
                "Unexpected exception on %s %s: %s",
                request.method,
                request.url.path,
                exc,
            )
            raise
        if response.status_code == 404:
            logger.warning(
                "404 Not Found: %s %s",
                request.method,
                request.url.path,
            )
        return response

    learner_repo = InMemoryLearnerProfileRepository()
    programme_repo = InMemoryUniversityProgrammeRepository()
    application_repo = InMemoryApplicationRepository()

    learner_svc = LearnerProfileService(
        learner_repo=learner_repo,
        application_repo=application_repo,
    )
    programme_svc = UniversityProgrammeService(programme_repo=programme_repo)
    application_svc = ApplicationService(
        application_repo=application_repo,
        learner_repo=learner_repo,
        programme_repo=programme_repo,
    )

    @fastapi_app.exception_handler(LearnerNotFoundError)
    async def _learner_404(request, exc):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @fastapi_app.exception_handler(ProgrammeNotFoundError)
    async def _programme_404(request, exc):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @fastapi_app.exception_handler(ApplicationNotFoundError)
    async def _application_404(request, exc):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @fastapi_app.exception_handler(TooManyActiveApplicationsError)
    async def _too_many(request, exc):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @fastapi_app.exception_handler(DuplicateApplicationError)
    async def _duplicate(request, exc):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @fastapi_app.exception_handler(ProgrammeNotActiveError)
    async def _not_active(request, exc):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @fastapi_app.exception_handler(InvalidStatusTransitionError)
    async def _bad_transition(request, exc):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @fastapi_app.exception_handler(ValueError)
    async def _value_error(request, exc):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    # ── /api/learners ────────────────────────────────────────────────────────

    @fastapi_app.get(
        "/api/learners",
        response_model=List[LearnerResponse],
        tags=["Learners"],
        summary="List all learner profiles",
    )
    async def list_learners():
        return [_learner_out(p) for p in learner_svc.list_profiles()]

    @fastapi_app.post(
        "/api/learners",
        response_model=LearnerResponse,
        status_code=201,
        tags=["Learners"],
        summary="Create a learner profile",
    )
    async def create_learner(payload: CreateLearnerRequest):
        profile = LearnerProfile(
            learner_id=uuid4(),
            full_name=payload.full_name,
            school_id_number=payload.school_id_number,
            grade=payload.grade,
            status=ProfileStatusEnum.Incomplete,
            counselor_id=payload.counselor_id,
            school_id=payload.school_id,
        )
        return _learner_out(learner_svc.create_profile(profile))

    @fastapi_app.get(
        "/api/learners/{learner_id}",
        response_model=LearnerResponse,
        tags=["Learners"],
        summary="Get a learner profile",
        responses={404: {"description": "Learner not found"}},
    )
    async def get_learner(learner_id: UUID):
        return _learner_out(learner_svc.get_profile(learner_id))

    @fastapi_app.put(
        "/api/learners/{learner_id}",
        response_model=LearnerResponse,
        tags=["Learners"],
        summary="Update a learner profile",
        responses={404: {"description": "Learner not found"}},
    )
    async def update_learner(learner_id: UUID, payload: UpdateLearnerRequest):
        updates = {k: v for k, v in payload.model_dump().items() if v is not None}
        return _learner_out(learner_svc.update_profile(learner_id, **updates))

    @fastapi_app.delete(
        "/api/learners/{learner_id}",
        status_code=204,
        tags=["Learners"],
        summary="Delete a learner profile",
        responses={404: {"description": "Learner not found"}},
    )
    async def delete_learner(learner_id: UUID):
        learner_svc.delete_profile(learner_id)

    @fastapi_app.post(
        "/api/learners/{learner_id}/marks",
        response_model=LearnerResponse,
        status_code=201,
        tags=["Learners"],
        summary="Add a mark to a learner profile",
        responses={
            404: {"description": "Learner not found"},
            422: {"description": "Invalid mark (e.g. score outside 0–100)"},
        },
    )
    async def add_mark(learner_id: UUID, payload: AddMarkRequest):
        mark = Mark(
            mark_id=uuid4(),
            learner_id=learner_id,
            subject_name=payload.subject_name,
            score=payload.score,
            exam_type=payload.exam_type,
            academic_year=payload.academic_year,
        )
        return _learner_out(learner_svc.add_mark(learner_id, mark))

    @fastapi_app.get(
        "/api/learners/{learner_id}/aps",
        response_model=ApsResponse,
        tags=["Learners"],
        summary="Get a learner's current APS score",
        responses={404: {"description": "Learner not found"}},
    )
    async def get_aps(learner_id: UUID):
        return ApsResponse(
            learner_id=learner_id,
            aps_score=learner_svc.get_aps_score(learner_id),
        )

    @fastapi_app.post(
        "/api/learners/{learner_id}/deactivate",
        response_model=LearnerResponse,
        tags=["Learners"],
        summary="Deactivate a learner profile",
        responses={404: {"description": "Learner not found"}},
    )
    async def deactivate_learner(learner_id: UUID):
        return _learner_out(learner_svc.deactivate_profile(learner_id))

    # ── /api/programmes ────────────────────────────────────────────────────

    @fastapi_app.get(
        "/api/programmes",
        response_model=List[ProgrammeResponse],
        tags=["Programmes"],
        summary="List all programmes",
    )
    async def list_programmes(
        published_only: bool = Query(False, description="Return only active published programmes"),
    ):
        if published_only:
            return [_programme_out(p) for p in programme_svc.list_published_programmes()]
        return [_programme_out(p) for p in programme_svc.list_programmes()]

    @fastapi_app.post(
        "/api/programmes",
        response_model=ProgrammeResponse,
        status_code=201,
        tags=["Programmes"],
        summary="Create a university programme",
    )
    async def create_programme(payload: CreateProgrammeRequest):
        programme = UniversityProgramme(
            programme_id=uuid4(),
            university_id=payload.university_id,
            name=payload.name,
            faculty=payload.faculty,
            minimum_aps=payload.minimum_aps,
            application_deadline=payload.application_deadline,
            application_fee=payload.application_fee,
            required_documents=payload.required_documents,
            status=ProgrammeStatusEnum.Draft,
            published_by=payload.published_by,
        )
        return _programme_out(programme_svc.create_programme(programme))

    @fastapi_app.get(
        "/api/programmes/{programme_id}",
        response_model=ProgrammeResponse,
        tags=["Programmes"],
        summary="Get a programme",
        responses={404: {"description": "Programme not found"}},
    )
    async def get_programme(programme_id: UUID):
        return _programme_out(programme_svc.get_programme(programme_id))

    @fastapi_app.put(
        "/api/programmes/{programme_id}",
        response_model=ProgrammeResponse,
        tags=["Programmes"],
        summary="Update a programme",
        responses={404: {"description": "Programme not found"}},
    )
    async def update_programme(programme_id: UUID, payload: UpdateProgrammeRequest):
        updates = {k: v for k, v in payload.model_dump().items() if v is not None}
        return _programme_out(programme_svc.update_programme(programme_id, **updates))

    @fastapi_app.delete(
        "/api/programmes/{programme_id}",
        status_code=204,
        tags=["Programmes"],
        summary="Delete a programme",
        responses={404: {"description": "Programme not found"}},
    )
    async def delete_programme(programme_id: UUID):
        programme_svc.delete_programme(programme_id)

    @fastapi_app.post(
        "/api/programmes/{programme_id}/publish",
        response_model=ProgrammeResponse,
        tags=["Programmes"],
        summary="Publish a programme",
        responses={
            404: {"description": "Programme not found"},
            400: {"description": "Deadline has passed; cannot publish"},
        },
    )
    async def publish_programme(programme_id: UUID):
        return _programme_out(programme_svc.publish_programme(programme_id))

    @fastapi_app.post(
        "/api/programmes/{programme_id}/deactivate",
        response_model=ProgrammeResponse,
        tags=["Programmes"],
        summary="Deactivate a programme",
        responses={404: {"description": "Programme not found"}},
    )
    async def deactivate_programme(programme_id: UUID):
        return _programme_out(programme_svc.deactivate_programme(programme_id))

    @fastapi_app.post(
        "/api/programmes/{programme_id}/extend-deadline",
        response_model=ProgrammeResponse,
        tags=["Programmes"],
        summary="Extend the application deadline",
        responses={404: {"description": "Programme not found"}},
    )
    async def extend_deadline(programme_id: UUID, payload: ExtendDeadlineRequest):
        return _programme_out(programme_svc.extend_deadline(programme_id, payload.new_deadline))

    @fastapi_app.get(
        "/api/programmes/{programme_id}/eligibility",
        response_model=EligibilityResponse,
        tags=["Programmes"],
        summary="Check a learner's eligibility for a programme",
        responses={404: {"description": "Programme not found"}},
    )
    async def check_eligibility(
        programme_id: UUID,
        learner_aps: int = Query(..., ge=0, le=42, description="The learner's APS score"),
    ):
        elig = programme_svc.check_eligibility(programme_id, learner_aps)
        prog = programme_svc.get_programme(programme_id)
        return EligibilityResponse(
            programme_id=programme_id,
            learner_aps=learner_aps,
            minimum_aps=prog.minimum_aps,
            eligibility=elig.value,
        )

    # ── /api/applications ───────────────────────────────────────────────────

    @fastapi_app.get(
        "/api/applications",
        response_model=List[ApplicationResponse],
        tags=["Applications"],
        summary="List all applications",
    )
    async def list_applications():
        return [_application_out(a) for a in application_svc.list_applications()]

    @fastapi_app.post(
        "/api/applications",
        response_model=ApplicationResponse,
        status_code=201,
        tags=["Applications"],
        summary="Create a new application",
        responses={
            404: {"description": "Learner or Programme not found"},
            409: {"description": "Duplicate application or programme not active"},
            422: {"description": "Active application limit reached"},
        },
    )
    async def create_application(payload: CreateApplicationRequest):
        created = application_svc.create_application(
            learner_id=payload.learner_id,
            programme_id=payload.programme_id,
            fee_amount=payload.fee_amount,
        )
        return _application_out(created)

    @fastapi_app.get(
        "/api/applications/learner/{learner_id}",
        response_model=List[ApplicationResponse],
        tags=["Applications"],
        summary="Get all applications for a learner",
        responses={404: {"description": "Learner not found"}},
    )
    async def list_learner_applications(learner_id: UUID):
        return [_application_out(a) for a in application_svc.list_for_learner(learner_id)]

    @fastapi_app.get(
        "/api/applications/{application_id}",
        response_model=ApplicationResponse,
        tags=["Applications"],
        summary="Get an application",
        responses={404: {"description": "Application not found"}},
    )
    async def get_application(application_id: UUID):
        return _application_out(application_svc.get_application(application_id))

    @fastapi_app.put(
        "/api/applications/{application_id}/status",
        response_model=ApplicationResponse,
        tags=["Applications"],
        summary="Update application status",
        responses={
            404: {"description": "Application not found"},
            422: {"description": "Invalid status transition"},
        },
    )
    async def update_status(application_id: UUID, payload: UpdateStatusRequest):
        return _application_out(
            application_svc.update_status(
                application_id, payload.new_status, payload.actor_id, payload.note
            )
        )

    @fastapi_app.post(
        "/api/applications/{application_id}/submit",
        response_model=ApplicationResponse,
        tags=["Applications"],
        summary="Submit an application",
        responses={
            404: {"description": "Application not found"},
            400: {"description": "Application is not ready to submit"},
        },
    )
    async def submit_application(application_id: UUID):
        return _application_out(application_svc.submit_application(application_id))

    @fastapi_app.post(
        "/api/applications/{application_id}/cancel",
        response_model=ApplicationResponse,
        tags=["Applications"],
        summary="Cancel an application",
        responses={
            404: {"description": "Application not found"},
            422: {"description": "Cannot cancel a terminal application"},
        },
    )
    async def cancel_application(application_id: UUID):
        return _application_out(application_svc.cancel_application(application_id))

    @fastapi_app.delete(
        "/api/applications/{application_id}",
        status_code=204,
        tags=["Applications"],
        summary="Hard-delete an application",
        responses={404: {"description": "Application not found"}},
    )
    async def delete_application(application_id: UUID):
        application_svc.delete_application(application_id)

    @fastapi_app.get("/health", tags=["Health"], summary="Health check")
    async def health():
        return {"status": "ok", "service": "UniMatch API", "version": "1.0.0"}

    return fastapi_app


app = create_app()
