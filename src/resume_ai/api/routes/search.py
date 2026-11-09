from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from resume_ai.core.database import get_db
from resume_ai.repository.candidate_repository import candidate_repository
from resume_ai.schemas.resume_schema import ResumeResponse
from resume_ai.schemas.search import (
    CandidateSearchRequest,
    CandidateSearchResponse,
    CandidateSearchResult,
    MatchedChunkResponse,
    SkillAssessmentResponse,
)
from resume_ai.services.candidate_reranking import candidate_reranking
from resume_ai.services.candidate_search import candidate_search

router = APIRouter(prefix="/search", tags=["Search"])


@router.get("", response_model=list[ResumeResponse])
async def get_candidate(db: AsyncSession = Depends(get_db)) -> list[ResumeResponse]:
    result = await candidate_repository.get_all(
        db=db,
    )
    return result


@router.post("", response_model=CandidateSearchResponse)
async def search_candidates(
    request: CandidateSearchRequest,
    db: AsyncSession = Depends(get_db),
) -> CandidateSearchResponse:
    matches = await candidate_search.execute(
        query=request.query,
        retrieval_limit=request.limit,
    )

    ranked_candidates = await candidate_reranking.execute(
        db=db,
        job_description=request.query,
        matches=matches,
    )

    candidates = [
        CandidateSearchResult(
            resume_id=str(candidate.resume.id),
            filename=candidate.resume.filename,
            semantic_score=candidate.match.score,
            match_score=candidate.evaluation.match_score,
            summary=candidate.evaluation.summary,
            skills=[
                SkillAssessmentResponse(
                    requirement=skill.requirement,
                    status=skill.status,
                    candidate_evidence=skill.candidate_evidence,
                )
                for skill in candidate.evaluation.skills
            ],
            relevant_experience=candidate.evaluation.relevant_experience,
            strengths=candidate.evaluation.strengths,
            gaps=candidate.evaluation.gaps,
            evidence=candidate.evaluation.evidence,
            matched_chunks=[
                MatchedChunkResponse(
                    chunk_index=chunk.chunk_index,
                    text=chunk.text,
                    score=chunk.score,
                )
                for chunk in candidate.match.matched_chunks
            ],
        )
        for candidate in ranked_candidates
    ]

    return CandidateSearchResponse(
        total=len(candidates),
        candidates=candidates,
    )
