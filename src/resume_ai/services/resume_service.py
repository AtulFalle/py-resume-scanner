import hashlib
import logging
from pathlib import Path
from uuid import UUID, uuid7

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from resume_ai.message_queue.publisher import publisher
from resume_ai.models.resume import FAILED_STATUSES, Resume
from resume_ai.storage.s3 import storage

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf"}
PDF_MAGIC = b"%PDF-"


class DuplicateResumeError(ValueError):
    def __init__(self, existing: Resume) -> None:
        super().__init__(
            f"'{existing.filename}' was already uploaded (resume id {existing.id}, "
            f"status {existing.status})."
        )
        self.existing = existing


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

        if not content.startswith(PDF_MAGIC):
            raise ValueError("The file is not a valid PDF")

        file_hash = hashlib.sha256(content).hexdigest()

        existing = await db.scalar(select(Resume).where(Resume.file_hash == file_hash).limit(1))
        if existing is not None:
            raise DuplicateResumeError(existing)

        resume_id = uuid7()
        object_name = f"{resume_id}{extension}"
        content_type = "application/pdf"

        # 1. Store the file in object storage.
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
            file_hash=file_hash,
            status="uploaded",
        )

        db.add(resume)
        await db.commit()
        await db.refresh(resume)

        # 3. Publish the processing job.
        await self._enqueue(db, resume)

        return {
            "id": resume.id,
            "name": resume.filename,
            "url": resume.object_name,
            "status": resume.status,
        }

    async def _enqueue(self, db: AsyncSession, resume: Resume) -> None:
        try:
            await publisher.publish_resume(
                resume_id=str(resume.id),
                object_name=resume.object_name,
            )
            resume.status = "queued"
            resume.error_message = None
            await db.commit()

        except Exception as error:
            resume.status = "queue_failed"
            resume.error_message = str(error)[:1000]
            await db.commit()
            raise RuntimeError("Resume uploaded but could not be queued") from error

    async def reprocess(self, db: AsyncSession, resume_id: UUID, force: bool = False) -> Resume:
        """Send a resume through extraction and embedding again."""
        resume = await db.get(Resume, resume_id)

        if resume is None:
            raise LookupError("Resume not found")

        in_progress = {"queued", "extracting", "embedding_queued", "embedding"}
        if resume.status in in_progress and not force:
            raise ValueError(f"Resume is already being processed (status {resume.status})")

        resume.retry_count = (resume.retry_count or 0) + 1
        await self._enqueue(db, resume)
        return resume

    async def reprocess_failed(self, db: AsyncSession) -> int:
        result = await db.execute(select(Resume).where(Resume.status.in_(FAILED_STATUSES)))
        resumes = list(result.scalars().all())

        requeued = 0
        for resume in resumes:
            try:
                resume.retry_count = (resume.retry_count or 0) + 1
                await self._enqueue(db, resume)
                requeued += 1
            except RuntimeError:
                logger.exception("Could not requeue resume %s", resume.id)

        return requeued

    async def download(self, db: AsyncSession, resume_id: UUID) -> tuple[Resume, bytes]:
        resume = await db.get(Resume, resume_id)
        if resume is None:
            raise LookupError("Resume not found")
        return resume, await storage.download(resume.object_name)


resume_service = ResumeService()
