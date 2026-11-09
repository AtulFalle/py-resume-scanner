from sqlalchemy.ext.asyncio import AsyncSession

from resume_ai.ai.tasks.candidate_reranking import (
    candidate_reranking_task,
)
from resume_ai.models.resume import Resume
from resume_ai.repository.candidate_repository import candidate_repository
from resume_ai.schemas.candidate_evaluation import CandidateEvaluation
from resume_ai.schemas.search import CandidateMatch


class RankedCandidate:
    def __init__(
        self,
        resume: Resume,
        match: CandidateMatch,
        evaluation: CandidateEvaluation,
    ) -> None:
        self.resume = resume
        self.match = match
        self.evaluation = evaluation


class CandidateReranking:
    SHORTLIST_SIZE = 10

    async def execute(
        self,
        db: AsyncSession,
        job_description: str,
        matches: list[CandidateMatch],
    ) -> list[RankedCandidate]:
        shortlist = matches[: self.SHORTLIST_SIZE]

        resume_ids = [match.resume_id for match in shortlist]

        resumes = await candidate_repository.get_by_ids(
            db=db,
            resume_ids=resume_ids,
        )

        ranked_candidates = []

        # Sequential execution because the current llama.cpp server
        # is configured with --parallel 1.
        for match in shortlist:
            resume = resumes.get(match.resume_id)

            if resume is None or not resume.extracted_text:
                continue

            evaluation = await candidate_reranking_task.execute(
                job_description=job_description,
                resume_text=resume.extracted_text,
            )

            ranked_candidates.append(
                RankedCandidate(
                    resume=resume,
                    match=match,
                    evaluation=evaluation,
                )
            )

        return sorted(
            ranked_candidates,
            key=lambda candidate: candidate.evaluation.match_score,
            reverse=True,
        )


candidate_reranking = CandidateReranking()
