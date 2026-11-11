import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import update

from resume_ai.core.database import SessionFactory
from resume_ai.message_queue.publisher import publisher
from resume_ai.models.research import ResumeResearch
from resume_ai.research.discovery import discover_urls
from dataclasses import asdict

logger = logging.getLogger(__name__)

RESEARCH_QUEUE = "resume.research"


class ResearchService:
    async def schedule(
        self,
        resume_id: UUID,
        extracted_text: str,
    ) -> None:
        discovered_urls = [
            asdict(discovered_url)
            for discovered_url in discover_urls(extracted_text)
        ]

        # 2. Create a research run.
        no_sources_found = not discovered_urls

        research = ResumeResearch(
            resume_id=resume_id,
            status="completed" if no_sources_found else "queued",
            discovered_urls=discovered_urls,
            source_results=[],
            report=(
                {
                    "status": "no_sources",
                    "summary": "No supported profile URLs were found in the resume.",
                    "sources": [],
                }
                if no_sources_found
                else None
            ),
            completed_at=datetime.now(UTC) if no_sources_found else None,
        )

        async with SessionFactory() as db:
            db.add(research)
            await db.commit()
            await db.refresh(research)

        logger.info(
            "Research run %s created for resume %s; URLs found: %d",
            research.id,
            resume_id,
            len(discovered_urls),
        )

        # No URLs means the research lifecycle is already complete.
        if no_sources_found:
            return

        # 3. Enqueue the independent research job.
        try:
            await publisher.publish_message(
                RESEARCH_QUEUE,
                {
                    "research_id": str(research.id),
                    "resume_id": str(resume_id),
                },
            )
        except Exception as error:
            logger.exception(
                "Could not enqueue research run %s",
                research.id,
            )

            async with SessionFactory() as db:
                await db.execute(
                    update(ResumeResearch)
                    .where(ResumeResearch.id == research.id)
                    .values(
                        status="failed",
                        error_message=str(error)[:1000],
                    )
                )
                await db.commit()


research_service = ResearchService()