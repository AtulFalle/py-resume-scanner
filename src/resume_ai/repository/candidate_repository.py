from uuid import UUID

from sqlalchemy import Select, Text, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from resume_ai.ai.skills import resume_skill_pattern
from resume_ai.models.candidate import CandidateProfile
from resume_ai.models.resume import COMPLETED_STATUS, FAILED_STATUSES, Resume

# Experience is often under-counted by date parsing, so allow a small margin.
EXPERIENCE_TOLERANCE_YEARS = 0.5


class CandidateRepository:
    async def get_by_ids(
        self,
        db: AsyncSession,
        resume_ids: list[str],
    ) -> dict[str, tuple[Resume, CandidateProfile | None]]:
        if not resume_ids:
            return {}

        ids = [UUID(resume_id) for resume_id in resume_ids]

        result = await db.execute(
            select(Resume, CandidateProfile)
            .outerjoin(CandidateProfile, CandidateProfile.resume_id == Resume.id)
            .where(Resume.id.in_(ids))
        )

        return {str(resume.id): (resume, profile) for resume, profile in result.all()}

    async def get_one(
        self,
        db: AsyncSession,
        resume_id: UUID,
    ) -> tuple[Resume, CandidateProfile | None] | None:
        result = await db.execute(
            select(Resume, CandidateProfile)
            .outerjoin(CandidateProfile, CandidateProfile.resume_id == Resume.id)
            .where(Resume.id == resume_id)
        )
        row = result.first()
        return (row[0], row[1]) if row else None

    def _list_query(
        self,
        status: str | None,
        category: str | None,
        text: str | None,
    ) -> Select:
        query = select(Resume, CandidateProfile).outerjoin(
            CandidateProfile, CandidateProfile.resume_id == Resume.id
        )

        if status:
            query = query.where(Resume.status == status)

        if category:
            query = query.where(CandidateProfile.category == category)

        if text:
            pattern = f"%{text.strip()}%"
            query = query.where(
                or_(
                    Resume.filename.ilike(pattern),
                    CandidateProfile.full_name.ilike(pattern),
                    CandidateProfile.primary_role.ilike(pattern),
                )
            )

        return query

    async def list_page(
        self,
        db: AsyncSession,
        offset: int,
        limit: int,
        status: str | None = None,
        category: str | None = None,
        text: str | None = None,
    ) -> tuple[int, list[tuple[Resume, CandidateProfile | None]]]:
        query = self._list_query(status, category, text)

        total = await db.scalar(select(func.count()).select_from(query.subquery()))

        result = await db.execute(
            query.order_by(Resume.created_at.desc()).offset(offset).limit(limit)
        )

        return int(total or 0), [(resume, profile) for resume, profile in result.all()]

    async def stats(self, db: AsyncSession) -> dict:
        status_rows = await db.execute(
            select(Resume.status, func.count()).group_by(Resume.status)
        )
        by_status = {status: count for status, count in status_rows.all()}

        category_rows = await db.execute(
            select(CandidateProfile.category, func.count())
            .join(Resume, Resume.id == CandidateProfile.resume_id)
            .where(Resume.status == COMPLETED_STATUS)
            .group_by(CandidateProfile.category)
        )
        by_category = {
            (category or "Unclassified"): count for category, count in category_rows.all()
        }

        total = sum(by_status.values())
        completed = by_status.get(COMPLETED_STATUS, 0)
        failed = sum(count for status, count in by_status.items() if status in FAILED_STATUSES)

        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "processing": total - completed - failed,
            "by_status": by_status,
            "by_category": by_category,
        }

    async def filter_searchable_ids(
        self,
        db: AsyncSession,
        required_skills: list[str],
        min_years: float | None,
        categories: list[str],
        include_unknown_experience: bool,
    ) -> list[str]:
        """Hard filters applied before vector search.

        Every required skill must appear (any known spelling) in the resume
        text or the extracted skill list. This is what keeps e.g. doctors out
        of an "Angular developer" search.
        """
        conditions = [Resume.status == COMPLETED_STATUS]

        for skill in required_skills:
            pattern = resume_skill_pattern(skill)
            if pattern is None:
                continue
            conditions.append(
                or_(
                    Resume.extracted_text.op("~*")(pattern),
                    cast(CandidateProfile.skills, Text).op("~*")(pattern),
                )
            )

        if min_years is not None and min_years > 0:
            threshold = max(0.0, min_years - EXPERIENCE_TOLERANCE_YEARS)
            years_ok = CandidateProfile.total_experience_years >= threshold
            if include_unknown_experience:
                years_ok = or_(years_ok, CandidateProfile.total_experience_years.is_(None))
            conditions.append(years_ok)

        if categories:
            # Unclassified resumes are kept; the LLM evaluation judges them.
            conditions.append(
                or_(
                    CandidateProfile.category.in_(categories),
                    CandidateProfile.category.is_(None),
                )
            )

        result = await db.execute(
            select(Resume.id)
            .outerjoin(CandidateProfile, CandidateProfile.resume_id == Resume.id)
            .where(and_(*conditions))
        )

        return [str(resume_id) for resume_id in result.scalars().all()]


candidate_repository = CandidateRepository()
