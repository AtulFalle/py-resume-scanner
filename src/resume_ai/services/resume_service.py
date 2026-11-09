from pathlib import Path
from uuid import uuid7

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from resume_ai.message_queue.publisher import publisher
from resume_ai.models.resume import Resume
from resume_ai.storage.s3 import storage

MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf"}


class ResumeService:
    async def upload(self, file: UploadFile, db: AsyncSession) -> dict:
        filename = file.filename or "resume.pdf"
        extension = Path(filename).suffix.lower()

        if extension not in ALLOWED_EXTENSIONS:
            raise ValueError("Only PDF files are allowed")

        content = await file.read(MAX_FILE_SIZE + 1)

        if not content:
            raise ValueError("The uploaded file is empty")

        if len(content) > MAX_FILE_SIZE:
            raise ValueError("File size cannot exceed 10 MB")

        resume_id = uuid7()
        object_name = f"{resume_id}{extension}"
        content_type = file.content_type or "application/pdf"

        # 1. Store the file in RustFS.
        await storage.upload(
            object_name=object_name,
            content=content,
            content_type=content_type,
        )

        # 2. Save resume metadata in PostgreSQL.
        resume = Resume(
            id=resume_id,
            filename=filename,
            object_name=object_name,
            content_type=content_type,
            file_size=len(content),
            status="uploaded",
        )

        db.add(resume)
        await db.commit()
        await db.refresh(resume)

        # 3. Publish the processing job.
        try:
            await publisher.publish_resume(
                resume_id=str(resume.id),
                object_name=object_name,
            )

            resume.status = "queued"
            await db.commit()

        except Exception as error:
            resume.status = "queue_failed"
            resume.error_message = str(error)[:1000]
            await db.commit()
            raise RuntimeError("Resume uploaded but could not be queued") from error

        return {
            "id": resume.id,
            "name": resume.filename,
            "url": resume.object_name,
            "status": resume.status,
        }


resume_service = ResumeService()
