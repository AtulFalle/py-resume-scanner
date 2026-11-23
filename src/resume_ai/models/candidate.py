import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from resume_ai.core.database import Base


class CandidateProfile(Base):
    """Searchable, structured view of a resume (one row per resume).

    Built deterministically from the LLM extraction result, so it can be
    rebuilt at any time without calling the LLM again.
    """

    __tablename__ = "candidate_profiles"

    resume_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("resumes.id", ondelete="CASCADE"),
        primary_key=True,
    )

    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    primary_role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    seniority: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    total_experience_years: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        index=True,
    )
    # "stated" (written in the resume), "computed" (from job dates) or None.
    experience_source: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Normalized skill names, lower-case.
    skills: Mapped[list[str]] = mapped_column(JSONB, default=list)
    domains: Mapped[list[str]] = mapped_column(JSONB, default=list)

    # [{"url": ..., "source_type": "linkedin" | "github" | "website"}]
    links: Mapped[list[dict]] = mapped_column(JSONB, default=list)

    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class CandidateEvaluationCache(Base):
    """LLM evaluation of one candidate against one set of search requirements."""

    __tablename__ = "candidate_evaluations"
    __table_args__ = (
        UniqueConstraint("resume_id", "cache_key", name="uq_candidate_evaluation"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid7)

    resume_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("resumes.id", ondelete="CASCADE"),
        index=True,
    )

    # Hash of requirements + prompt version + candidate content.
    cache_key: Mapped[str] = mapped_column(String(64))

    result: Mapped[dict] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
