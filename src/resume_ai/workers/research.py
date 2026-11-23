import asyncio
import logging
from uuid import UUID

from resume_ai.core.database import close_database
from resume_ai.message_queue.consumer import RabbitMQConsumer
from resume_ai.services.research_service import research_service

logger = logging.getLogger(__name__)

QUEUE_NAME = "resume.research"


async def process_research(payload: dict) -> None:
    research_id = UUID(payload["research_id"])
    logger.info(
        "Processing research run %s for resume %s",
        research_id,
        payload.get("resume_id"),
    )
    await research_service.run(research_id)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    consumer = RabbitMQConsumer(QUEUE_NAME)

    try:
        await consumer.start(process_research)
    finally:
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
