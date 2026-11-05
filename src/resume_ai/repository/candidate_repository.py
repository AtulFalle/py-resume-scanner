
from typing import List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from resume_ai.models.resume import Resume
from resume_ai.schemas.resume_schema import ResumeUploadResponse


class CandidateRepository:
    async def get_by_ids(
        self,
        db: AsyncSession,
        resume_ids: list[str],
    ) -> List[Resume]:
        if not resume_ids:
            return {}

        ids = [UUID(resume_id) for resume_id in resume_ids]

        result = await db.execute(
            select(Resume).where(Resume.id.in_(ids))
        )

        resumes = result.scalars().all()

        return {
            str(resume.id): resume
            for resume in resumes
        }

    async def get_all(self,
                      db: AsyncSession ) -> List[ResumeUploadResponse]:
        result = await db.execute(
            select(Resume)
        )
        return result.scalars().all()


candidate_repository = CandidateRepository()
