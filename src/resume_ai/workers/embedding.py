
import asyncio
import logging
from uuid import UUID

from sqlalchemy import select, update

from resume_ai.ai.tasks.resume_embedding import resume_embedding_task
from resume_ai.core.database import SessionFactory, close_database
from resume_ai.message_queue.consumer import RabbitMQConsumer
from resume_ai.models.resume import Resume
from resume_ai.storage.qdrant import qdrant_storage

logger = logging.getLogger(__name__)

QUEUE_NAME = "resume.embedding"


async def process_embedding(payload: dict) -> None:
    resume_id = UUID(payload["resume_id"])

    # Claim the job so duplicate messages cannot process it.
    async with SessionFactory() as db:
        result = await db.execute(
            update(Resume)
            .where(
                Resume.id == resume_id,
                Resume.status == "embedding_queued",
            )
            .values(
                status="embedding",
                error_message=None,
            )
            .returning(Resume.extracted_text)
        )

        document_text = result.scalar_one_or_none()
        await db.commit()

    if document_text is None:
        logger.info(
            "Skipping embedding for %s: no queued text or already processed",
            resume_id,
        )
        return

    try:
        # Generate vectors for all resume chunks.
        chunks, vectors = await resume_embedding_task.execute(
            document_text
        )

        # Store all vectors in Qdrant.
        await qdrant_storage.upsert_chunks(
            resume_id=str(resume_id),
            chunks=chunks,
            vectors=vectors,
        )

        # Mark processing complete.
        async with SessionFactory() as db:
            await db.execute(
                update(Resume)
                .where(
                    Resume.id == resume_id,
                    Resume.status == "embedding",
                )
                .values(
                    status="embedded",
                    error_message=None,
                )
            )
            await db.commit()

        logger.info("Resume embedding completed: %s", resume_id)

    except Exception as error:
        logger.exception("Embedding failed for resume %s", resume_id)

        async with SessionFactory() as db:
            await db.execute(
                update(Resume)
                .where(
                    Resume.id == resume_id,
                    Resume.status == "embedding",
                )
                .values(
                    status="embedding_failed",
                    error_message=str(error)[:1000],
                    retry_count=Resume.retry_count + 1,
                )
            )
            await db.commit()

        raise


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    consumer = RabbitMQConsumer(QUEUE_NAME)

    try:
        await qdrant_storage.ensure_collection()
        await consumer.start(process_embedding)
    finally:
        await qdrant_storage.close()
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
