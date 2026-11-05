from fastapi import APIRouter

from resume_ai.ai.tasks.resume_extractor import resume_extraction_task
from resume_ai.schemas.resume_schema import (
    ResumeExtraction,
    ResumeExtractionRequest,
)

router = APIRouter(prefix="/ai", tags=["AI"])


@router.get("/health")
async def ai_health() -> dict[str, str]:
    return {
        "status": "healthy",
        "service": "ai",
    }


@router.post(
    "/resumes/extract",
    response_model=ResumeExtraction,
)
async def extract_resume(
    request: ResumeExtractionRequest,
) -> ResumeExtraction:
    return await resume_extraction_task.execute(request.document_text)
