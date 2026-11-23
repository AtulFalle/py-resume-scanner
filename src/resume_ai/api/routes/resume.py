from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from resume_ai.core.database import get_db
from resume_ai.models.candidate import CandidateProfile
from resume_ai.models.resume import Resume
from resume_ai.repository.candidate_repository import candidate_repository
from resume_ai.schemas.resume_schema import (
    ResumePage,
    ResumeResponse,
    ResumeStats,
    ResumeSummary,
    ResumeUploadResponse,
)
from resume_ai.services.research_service import research_service, serialize_research
from resume_ai.services.resume_service import DuplicateResumeError, resume_service

router = APIRouter(prefix="/resumes", tags=["Resumes"])

PROFILE_FIELDS = (
    "full_name",
    "email",
    "phone",
    "location",
    "primary_role",
    "category",
    "seniority",
    "total_experience_years",
    "experience_source",
    "skills",
    "domains",
    "links",
    "summary",
)


class ManualProfileRequest(BaseModel):
    source_type: str = Field(default="linkedin", pattern="^(linkedin|website|github|other)$")
    url: str | None = Field(default=None, max_length=2000)
    text: str = Field(min_length=20, max_length=20000)


def _summary(resume: Resume, profile: CandidateProfile | None) -> ResumeSummary:
    summary = ResumeSummary.model_validate(resume)
    if profile is not None:
        summary.full_name = profile.full_name
        summary.primary_role = profile.primary_role
        summary.category = profile.category
        summary.seniority = profile.seniority
        summary.total_experience_years = profile.total_experience_years
        summary.location = profile.location
    return summary


def _profile_dict(profile: CandidateProfile | None) -> dict | None:
    if profile is None:
        return None
    return {field: getattr(profile, field) for field in PROFILE_FIELDS}


@router.post("/upload", response_model=ResumeUploadResponse, status_code=201)
async def upload_resume(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await resume_service.upload(file, db)

    except DuplicateResumeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("", response_model=ResumePage)
async def list_resumes(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    status: str | None = None,
    category: str | None = None,
    q: str | None = Query(default=None, max_length=200),
    db: AsyncSession = Depends(get_db),
) -> ResumePage:
    total, rows = await candidate_repository.list_page(
        db=db,
        offset=offset,
        limit=limit,
        status=status or None,
        category=category or None,
        text=q or None,
    )
    return ResumePage(
        total=total,
        offset=offset,
        limit=limit,
        items=[_summary(resume, profile) for resume, profile in rows],
    )


@router.get("/stats", response_model=ResumeStats)
async def resume_stats(db: AsyncSession = Depends(get_db)) -> ResumeStats:
    return ResumeStats(**await candidate_repository.stats(db))


@router.post("/reprocess-failed")
async def reprocess_failed(db: AsyncSession = Depends(get_db)) -> dict:
    return {"requeued": await resume_service.reprocess_failed(db)}


@router.get("/{resume_id}")
async def get_resume(resume_id: UUID, db: AsyncSession = Depends(get_db)) -> dict:
    record = await candidate_repository.get_one(db, resume_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Resume not found")

    resume, profile = record
    research = await research_service.get_latest(db, resume_id)

    return {
        **ResumeResponse.model_validate(resume).model_dump(mode="json"),
        "profile": _profile_dict(profile),
        "research": serialize_research(research) if research else None,
    }


@router.get("/{resume_id}/file")
async def download_resume(resume_id: UUID, db: AsyncSession = Depends(get_db)) -> Response:
    try:
        resume, content = await resume_service.download(db, resume_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    safe_name = resume.filename.replace('"', "")
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{safe_name}"'},
    )


@router.post("/{resume_id}/reprocess")
async def reprocess_resume(
    resume_id: UUID,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        resume = await resume_service.reprocess(db, resume_id, force=force)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    return {"id": str(resume.id), "status": resume.status}


@router.post("/{resume_id}/research")
async def rerun_research(resume_id: UUID) -> dict:
    try:
        run = await research_service.rerun(resume_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    return serialize_research(run)


@router.post("/{resume_id}/research/manual")
async def add_manual_profile(resume_id: UUID, request: ManualProfileRequest) -> dict:
    try:
        run = await research_service.add_manual_profile(
            resume_id=resume_id,
            source_type=request.source_type,
            url=request.url,
            text=request.text,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return serialize_research(run)
