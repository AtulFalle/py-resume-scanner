import asyncio
import logging
from io import BytesIO
from uuid import UUID

from pypdf import PdfReader
from sqlalchemy import update

from resume_ai.ai.runtime import llm_runtime
from resume_ai.ai.tasks.resume_extractor import resume_extraction_task
from resume_ai.core.database import SessionFactory, close_database
from resume_ai.message_queue.consumer import RabbitMQConsumer
from resume_ai.message_queue.publisher import publisher
from resume_ai.models.resume import Resume
from resume_ai.storage.s3 import storage

logger = logging.getLogger(__name__)

QUEUE_NAME = "resume.processing"
NEXT_QUEUE = "resume.embedding"


async def mark_failed(resume_id: UUID, error: str) -> None:
    async with SessionFactory() as db:
        await db.execute(
            update(Resume)
            .where(Resume.id == resume_id)
            .values(
                status="failed",
                error_message=error[:1000],
            )
        )
        await db.commit()


async def process_resume(payload: dict) -> None:
    resume_id = UUID(payload["resume_id"])

    # 1. Atomically claim the job.
    async with SessionFactory() as db:
        result = await db.execute(
            update(Resume)
            .where(
                Resume.id == resume_id,
                Resume.status == "queued",
            )
            .values(
                status="extracting",
                error_message=None,
            )
            .returning(Resume.object_name)
        )

        object_name = result.scalar_one_or_none()
        await db.commit()

    # Already processed, claimed, or invalid job.
    # Acknowledge it rather than processing it twice.
    if object_name is None:
        logger.info("Skipping resume %s: not queued", resume_id)
        return

    try:
        # 2. Download from RustFS.
        file_content = await storage.download(object_name)

        # 3. Extract PDF text.
        reader = PdfReader(BytesIO(file_content))

        document_text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()

        if not document_text:
            raise ValueError("No extractable text found in PDF. Scanned PDFs require OCR support.")

        # 4. Run the existing AI extraction task.
        extraction = await resume_extraction_task.execute(document_text)

        # 5. Save results and advance lifecycle.
        async with SessionFactory() as db:
            await db.execute(
                update(Resume)
                .where(
                    Resume.id == resume_id,
                    Resume.status == "extracting",
                )
                .values(
                    extracted_text=document_text,
                    extraction_result=extraction.model_dump(mode="json"),
                    status="embedding_queued",
                    error_message=None,
                )
            )
            await db.commit()

        # 6. Publish the next-stage job.
        await publisher.publish_message(
            NEXT_QUEUE,
            {
                "resume_id": str(resume_id),
            },
        )

        logger.info("Resume %s extraction completed", resume_id)

    except Exception as error:
        logger.exception("Resume extraction failed: %s", resume_id)
        await mark_failed(resume_id, str(error))
        raise


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    consumer = RabbitMQConsumer(QUEUE_NAME)

    try:
        await llm_runtime.start()
        await consumer.start(process_resume)
    finally:
        await publisher.close()
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
