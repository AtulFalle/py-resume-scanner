from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from resume_ai.core.database import get_db
from resume_ai.schemas.resume_schema import ResumeUploadResponse
from resume_ai.services.resume_service import resume_service

router = APIRouter(prefix="/resumes", tags=["Resumes"])


@router.post("/upload", response_model=ResumeUploadResponse, status_code=201)
async def upload_resume(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await resume_service.upload(file, db)

    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
