"""Candidate search pipeline.

1. Parse the query into requirements (small LLM call, cached) and apply the
   recruiter's explicit filters on top.
2. Hard-filter resumes in Postgres: required skills, minimum years, category.
   Cheap, deterministic, and the reason unrelated professions never show up.
3. Vector search restricted to the resumes that passed.
4. LLM evaluation of the top N (cached per query + candidate).
5. Drop anything below the minimum match score.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from resume_ai.ai.aggregate import candidate_aggregation
from resume_ai.ai.retrival import candidate_retrieval
from resume_ai.ai.tasks.query_embedding import query_embedding
from resume_ai.ai.tasks.query_parser import query_parser
from resume_ai.core.config import settings
from resume_ai.repository.candidate_repository import candidate_repository
from resume_ai.schemas.search import (
    CandidateLink,
    CandidateSearchRequest,
    CandidateSearchResponse,
    CandidateSearchResult,
    MatchedChunkResponse,
    SearchRequirements,
    SearchStats,
    SkillAssessmentResponse,
)
from resume_ai.services.candidate_reranking import RankedCandidate, candidate_reranking

logger = logging.getLogger(__name__)

# Above this many pre-filtered ids, filter Qdrant results in code instead.
MAX_IDS_IN_VECTOR_FILTER = 20000


def _embedding_text(requirements: SearchRequirements, query: str) -> str:
    parts = [requirements.search_text or query]
    skills = [*requirements.required_skills, *requirements.preferred_skills]
    if requirements.role and requirements.role.lower() not in parts[0].lower():
        parts.insert(0, requirements.role)
    if skills:
        parts.append("Skills: " + ", ".join(skills))
    return ". ".join(parts)


def _to_result(candidate: RankedCandidate) -> CandidateSearchResult:
    resume, profile, match, evaluation = (
        candidate.resume,
        candidate.profile,
        candidate.match,
        candidate.evaluation,
    )

    return CandidateSearchResult(
        resume_id=str(resume.id),
        filename=resume.filename,
        full_name=profile.full_name if profile else None,
        primary_role=profile.primary_role if profile else None,
        category=profile.category if profile else None,
        seniority=profile.seniority if profile else None,
        location=profile.location if profile else None,
        total_experience_years=profile.total_experience_years if profile else None,
        experience_source=profile.experience_source if profile else None,
        links=[CandidateLink(**link) for link in (profile.links if profile else []) or []],
        semantic_score=match.score,
        match_score=evaluation.match_score,
        profession_match=evaluation.profession_match,
        summary=evaluation.summary,
        skills=[
            SkillAssessmentResponse(
                requirement=skill.requirement,
                required=skill.required,
                status=skill.status,
                candidate_evidence=skill.candidate_evidence,
            )
            # Required requirements first.
            for skill in sorted(evaluation.skills, key=lambda item: not item.required)
        ],
        relevant_experience=evaluation.relevant_experience,
        strengths=evaluation.strengths,
        gaps=evaluation.gaps,
        evidence=evaluation.evidence,
        matched_chunks=[
            MatchedChunkResponse(
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                score=chunk.score,
            )
            for chunk in match.matched_chunks
        ],
    )


class CandidateSearch:
    async def resolve_requirements(self, request: CandidateSearchRequest) -> SearchRequirements:
        requirements = await query_parser.execute(request.query)

        if request.required_skills is not None:
            requirements.required_skills = SearchRequirements(
                required_skills=request.required_skills
            ).required_skills

        if request.categories is not None:
            requirements.categories = list(request.categories)

        if request.min_years is not None:
            requirements.min_years = request.min_years or None

        return requirements

    async def execute(
        self,
        db: AsyncSession,
        request: CandidateSearchRequest,
    ) -> CandidateSearchResponse:
        query = request.query.strip()
        if not query:
            raise ValueError("Search query cannot be empty")

        min_score = (
            request.min_score if request.min_score is not None else settings.search_min_match_score
        )
        requirements = await self.resolve_requirements(request)
        stats = SearchStats(min_score=min_score)

        def respond(candidates: list[CandidateSearchResult], message: str | None = None):
            return CandidateSearchResponse(
                total=len(candidates),
                requirements=requirements,
                stats=stats,
                message=message,
                candidates=candidates,
            )

        # The skill filter is precise; the category filter is a coarse fallback
        # used when no skills are given (or when the recruiter picked categories).
        apply_categories = bool(requirements.categories) and (
            request.categories is not None or not requirements.required_skills
        )
        categories = list(requirements.categories) if apply_categories else []

        allowed_ids: list[str] | None = None
        if requirements.required_skills or requirements.min_years or categories:
            allowed_ids = await candidate_repository.filter_searchable_ids(
                db=db,
                required_skills=requirements.required_skills,
                min_years=requirements.min_years,
                categories=categories,
                include_unknown_experience=request.include_unknown_experience,
            )
            stats.passed_filters = len(allowed_ids)

            if not allowed_ids:
                return respond([], self._no_filter_match_message(requirements, categories))

        vector = await query_embedding.execute(_embedding_text(requirements, query))

        use_vector_filter = allowed_ids is not None and len(allowed_ids) <= MAX_IDS_IN_VECTOR_FILTER
        chunks = await candidate_retrieval.execute(
            query_vector=vector,
            # Enough chunks that every pre-filtered resume can be returned.
            limit=max(settings.search_retrieval_limit, len(allowed_ids or []) * 10),
            resume_ids=allowed_ids if use_vector_filter else None,
        )

        if allowed_ids is not None and not use_vector_filter:
            allowed = set(allowed_ids)
            chunks = [chunk for chunk in chunks if chunk.resume_id in allowed]

        matches = candidate_aggregation.execute(chunks)
        stats.retrieved = len(matches)

        if not matches:
            return respond([], "No indexed resumes matched this search.")

        # Every match is evaluated unless the caller explicitly caps it.
        shortlist = matches[: request.limit] if request.limit else matches
        ranked = await candidate_reranking.execute(
            db=db,
            job_description=query,
            requirements=requirements,
            matches=shortlist,
        )
        stats.evaluated = len(ranked)

        qualified = [item for item in ranked if item.evaluation.match_score >= min_score]
        stats.below_threshold = len(ranked) - len(qualified)

        message = None
        if not qualified:
            message = (
                f"{len(ranked)} candidate(s) were evaluated but none scored {min_score} or "
                "higher. Try fewer required skills, a lower minimum score, or a broader query."
            )
        elif stats.below_threshold:
            message = (
                f"{stats.below_threshold} weaker candidate(s) scoring below {min_score} "
                "were hidden."
            )

        return respond([_to_result(item) for item in qualified], message)

    @staticmethod
    def _no_filter_match_message(requirements: SearchRequirements, categories: list[str]) -> str:
        parts = []
        if requirements.required_skills:
            parts.append("all required skills (" + ", ".join(requirements.required_skills) + ")")
        if requirements.min_years:
            parts.append(f"at least {requirements.min_years:g} years of experience")
        if categories:
            parts.append("category " + " / ".join(categories))
        return (
            "No processed resumes have "
            + " and ".join(parts)
            + ". Remove a required skill or lower the experience filter to broaden the search."
        )


candidate_search = CandidateSearch()
