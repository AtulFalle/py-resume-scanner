"""Build the searchable candidate profile from an extraction result.

Pure code, no LLM calls, so it can be re-run for every resume cheaply
(see `python -m resume_ai.scripts.backfill_profiles`).
"""

from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from resume_ai.ai.experience import compute_experience_years, parse_stated_experience
from resume_ai.ai.skills import normalize_skill
from resume_ai.models.candidate import CandidateProfile
from resume_ai.research.discovery import discover_urls
from resume_ai.schemas.resume_schema import ResumeExtraction


def build_profile_values(
    resume_id: UUID,
    extraction: ResumeExtraction,
    document_text: str,
    pdf_link_urls: list[str] | None = None,
) -> dict:
    profile = extraction.candidate_profile

    stated_years = parse_stated_experience(extraction.total_experience)
    computed_years = compute_experience_years(
        (job.start_date, job.end_date) for job in extraction.work_experience
    )

    if stated_years is not None:
        years, source = stated_years, "stated"
    elif computed_years is not None:
        years, source = computed_years, "computed"
    else:
        # Last resort: a claim in the summary, e.g. "8+ years of experience".
        summary_years = parse_stated_experience(extraction.summary)
        years, source = (summary_years, "stated") if summary_years is not None else (None, None)

    skills: list[str] = []
    seen: set[str] = set()
    for skill in [
        *(item.normalized_name for item in profile.skills),
        *extraction.skills,
    ]:
        normalized = normalize_skill(skill)
        if normalized and normalized not in seen:
            seen.add(normalized)
            skills.append(normalized)

    links = [
        {"url": item.normalized_url, "source_type": item.source_type}
        for item in discover_urls(document_text, extra_urls=pdf_link_urls or [])
    ]

    return {
        "resume_id": resume_id,
        "full_name": _clip(extraction.full_name, 255),
        "email": _clip(extraction.email, 255),
        "phone": _clip(extraction.phone, 64),
        "location": _clip(extraction.location, 255),
        "primary_role": _clip(profile.primary_role, 255),
        "category": profile.category,
        "seniority": profile.seniority,
        "total_experience_years": years,
        "experience_source": source,
        "skills": skills,
        "domains": [normalize_skill(domain) for domain in profile.domains if domain.strip()],
        "links": links,
        "summary": extraction.summary,
    }


def _clip(value: str | None, length: int) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value[:length] or None


async def upsert_profile(db: AsyncSession, values: dict) -> None:
    statement = insert(CandidateProfile).values(**values)
    statement = statement.on_conflict_do_update(
        index_elements=[CandidateProfile.resume_id],
        set_={key: value for key, value in values.items() if key != "resume_id"},
    )
    await db.execute(statement)

