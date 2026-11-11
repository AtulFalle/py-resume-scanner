import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from resume_ai.core.database import Base


class ResumeResearch(Base):
    __tablename__ = "resume_research"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid7,
    )

    resume_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("resumes.id", ondelete="CASCADE"),
        index=True,
    )

    # queued, processing, completed, partial, failed
    status: Mapped[str] = mapped_column(
        String(30),
        default="queued",
        index=True,
    )

    # URLs discovered in the extracted resume text.
    discovered_urls: Mapped[list[dict]] = mapped_column(
        JSONB,
        default=list,
    )

    # Provider-level outcomes, evidence and retrieval metadata.
    source_results: Mapped[list[dict]] = mapped_column(
        JSONB,
        default=list,
    )

    # Consolidated recruiter-facing report.
    report: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    retry_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )