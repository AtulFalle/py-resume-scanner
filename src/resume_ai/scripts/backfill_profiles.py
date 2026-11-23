"""Rebuild candidate profiles for resumes that were processed before profiles existed.

No LLM calls: it reuses the stored extraction result. Optionally re-reads each
PDF to pick up clickable link targets.

    uv run python -m resume_ai.scripts.backfill_profiles            # missing only
    uv run python -m resume_ai.scripts.backfill_profiles --all      # rebuild all
    uv run python -m resume_ai.scripts.backfill_profiles --no-pdf   # skip PDF downloads
"""

import argparse
import asyncio
import logging

from sqlalchemy import select

from resume_ai.core.database import SessionFactory, close_database, create_tables
from resume_ai.models.candidate import CandidateProfile
from resume_ai.models.resume import Resume
from resume_ai.research.discovery import extract_pdf_link_targets
from resume_ai.schemas.resume_schema import ResumeExtraction
from resume_ai.services.candidate_profile import build_profile_values, upsert_profile
from resume_ai.storage.s3 import storage

logger = logging.getLogger(__name__)


async def backfill(rebuild_all: bool, read_pdf: bool) -> None:
    await create_tables()

    async with SessionFactory() as db:
        query = select(Resume).where(
            Resume.extraction_result.is_not(None),
            Resume.extracted_text.is_not(None),
        )
        if not rebuild_all:
            query = query.outerjoin(
                CandidateProfile, CandidateProfile.resume_id == Resume.id
            ).where(CandidateProfile.resume_id.is_(None))

        resumes = list((await db.execute(query)).scalars().all())

    logger.info("Backfilling %d resume profile(s)", len(resumes))
    done = failed = 0

    for resume in resumes:
        try:
            extraction = ResumeExtraction.model_validate(resume.extraction_result)

            pdf_links: list[str] = []
            if read_pdf:
                try:
                    pdf_links = extract_pdf_link_targets(
                        await storage.download(resume.object_name)
                    )
                except Exception:
                    logger.warning("Could not read PDF for %s; continuing", resume.id)

            values = build_profile_values(
                resume.id, extraction, resume.extracted_text or "", pdf_links
            )

            async with SessionFactory() as db:
                await upsert_profile(db, values)
                await db.commit()
            done += 1

        except Exception:
            failed += 1
            logger.exception("Could not build profile for resume %s", resume.id)

    logger.info("Backfill finished: %d updated, %d failed", done, failed)


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="rebuild every profile")
    parser.add_argument("--no-pdf", action="store_true", help="don't download PDFs for links")
    args = parser.parse_args()

    async def run() -> None:
        try:
            await backfill(rebuild_all=args.all, read_pdf=not args.no_pdf)
        finally:
            await close_database()

    asyncio.run(run())


if __name__ == "__main__":
    main()
