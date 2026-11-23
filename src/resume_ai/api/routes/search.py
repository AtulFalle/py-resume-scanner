from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from resume_ai.core.database import get_db
from resume_ai.schemas.resume_schema import RESUME_CATEGORIES
from resume_ai.schemas.search import CandidateSearchRequest, CandidateSearchResponse
from resume_ai.services.candidate_search import candidate_search

router = APIRouter(prefix="/search", tags=["Search"])


@router.get("/categories", response_model=list[str])
async def list_categories() -> list[str]:
    return RESUME_CATEGORIES


@router.post("", response_model=CandidateSearchResponse)
async def search_candidates(
    request: CandidateSearchRequest,
    db: AsyncSession = Depends(get_db),
) -> CandidateSearchResponse:
    try:
        return await candidate_search.execute(db=db, request=request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
