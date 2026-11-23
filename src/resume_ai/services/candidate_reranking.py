import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from resume_ai.ai.tasks.candidate_reranking import PROMPT_VERSION, candidate_reranking_task
from resume_ai.core.config import settings
from resume_ai.models.candidate import CandidateEvaluationCache, CandidateProfile
from resume_ai.models.resume import Resume
from resume_ai.repository.candidate_repository import candidate_repository
from resume_ai.schemas.candidate_evaluation import CandidateEvaluation
from resume_ai.schemas.search import CandidateMatch, SearchRequirements
from resume_ai.services.research_service import research_service

logger = logging.getLogger(__name__)

PROFESSION_MISMATCH_CAP = 15
MISSING_REQUIRED_SKILL_CAP = 45
UNKNOWN_EXPERIENCE_CAP = 75


@dataclass
class RankedCandidate:
    resume: Resume
    profile: CandidateProfile | None
    match: CandidateMatch
    evaluation: CandidateEvaluation


def _cache_key(
    query: str,
    requirements: SearchRequirements,
    resume_text: str,
    supplementary: str,
) -> str:
    payload = {
        "prompt_version": PROMPT_VERSION,
        "query": " ".join(query.lower().split()),
        "requirements": requirements.model_dump(mode="json", exclude={"search_text"}),
        "content": hashlib.sha256((resume_text + "\n" + supplementary).encode()).hexdigest(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def apply_score_caps(
    evaluation: CandidateEvaluation,
    requirements: SearchRequirements,
    profile: CandidateProfile | None,
) -> CandidateEvaluation:
    """Enforce the scoring rules in code, in case the model doesn't."""
    score = evaluation.match_score
    gaps = list(evaluation.gaps)

    if not evaluation.profession_match:
        score = min(score, PROFESSION_MISMATCH_CAP)

    if any(skill.required and skill.status == "missing" for skill in evaluation.skills):
        score = min(score, MISSING_REQUIRED_SKILL_CAP)

    years = profile.total_experience_years if profile else None
    if requirements.min_years and years is None:
        score = min(score, UNKNOWN_EXPERIENCE_CAP)
        note = "Total experience not stated in the resume"
        if note not in gaps:
            gaps.append(note)

    return evaluation.model_copy(update={"match_score": score, "gaps": gaps})


class CandidateReranking:
    async def execute(
        self,
        db: AsyncSession,
        job_description: str,
        requirements: SearchRequirements,
        matches: list[CandidateMatch],
    ) -> list[RankedCandidate]:
        if not matches:
            return []

        resume_ids = [match.resume_id for match in matches]
        records = await candidate_repository.get_by_ids(db=db, resume_ids=resume_ids)

        try:
            supplementary = await research_service.supplementary_text(db, resume_ids)
        except Exception:
            logger.exception("Could not load supplementary profile data")
            supplementary = {}

        # Load cached evaluations.
        keys: dict[str, str] = {}
        for match in matches:
            record = records.get(match.resume_id)
            if record is None or not record[0].extracted_text:
                continue
            keys[match.resume_id] = _cache_key(
                job_description,
                requirements,
                record[0].extracted_text,
                supplementary.get(match.resume_id, ""),
            )

        cached: dict[str, CandidateEvaluation] = {}
        if keys:
            rows = await db.execute(
                select(CandidateEvaluationCache).where(
                    CandidateEvaluationCache.resume_id.in_([UUID(rid) for rid in keys]),
                    CandidateEvaluationCache.cache_key.in_(list(keys.values())),
                )
            )
            for row in rows.scalars().all():
                resume_id = str(row.resume_id)
                if keys.get(resume_id) == row.cache_key:
                    try:
                        cached[resume_id] = CandidateEvaluation.model_validate(row.result)
                    except ValueError:
                        pass

        # Evaluate the rest with bounded concurrency.
        semaphore = asyncio.Semaphore(max(1, settings.search_evaluation_concurrency))

        async def evaluate(resume_id: str) -> tuple[str, CandidateEvaluation | None]:
            resume = records[resume_id][0]
            async with semaphore:
                try:
                    evaluation = await candidate_reranking_task.execute(
                        job_description=job_description,
                        requirements=requirements,
                        resume_text=resume.extracted_text or "",
                        supplementary=supplementary.get(resume_id),
                    )
                    return resume_id, evaluation
                except Exception:
                    logger.exception("Evaluation failed for resume %s", resume_id)
                    return resume_id, None

        pending = [resume_id for resume_id in keys if resume_id not in cached]
        fresh = dict(await asyncio.gather(*(evaluate(resume_id) for resume_id in pending)))

        for resume_id, evaluation in fresh.items():
            if evaluation is None:
                continue
            await db.execute(
                insert(CandidateEvaluationCache)
                .values(
                    resume_id=UUID(resume_id),
                    cache_key=keys[resume_id],
                    result=evaluation.model_dump(mode="json"),
                )
                .on_conflict_do_nothing(constraint="uq_candidate_evaluation")
            )
        if fresh:
            await db.commit()

        ranked: list[RankedCandidate] = []
        for match in matches:
            evaluation = cached.get(match.resume_id) or fresh.get(match.resume_id)
            if evaluation is None:
                continue
            resume, profile = records[match.resume_id]
            ranked.append(
                RankedCandidate(
                    resume=resume,
                    profile=profile,
                    match=match,
                    evaluation=apply_score_caps(evaluation, requirements, profile),
                )
            )

        return sorted(
            ranked,
            key=lambda candidate: (candidate.evaluation.match_score, candidate.match.score),
            reverse=True,
        )


candidate_reranking = CandidateReranking()
