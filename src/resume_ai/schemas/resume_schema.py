from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid7

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

ResumeCategory = Literal[
    "HR",
    "Designer",
    "Information-Technology",
    "Teacher",
    "Advocate",
    "Business-Development",
    "Healthcare",
    "Fitness",
    "Agriculture",
    "BPO",
    "Sales",
    "Consultant",
    "Digital-Media",
    "Automobile",
    "Chef",
    "Finance",
    "Apparel",
    "Engineering",
    "Accountant",
    "Construction",
    "Public-Relations",
    "Banking",
    "Arts",
    "Aviation",
]

RESUME_CATEGORIES: list[str] = list(ResumeCategory.__args__)  # type: ignore[attr-defined]

Seniority = Literal[
    "entry",
    "junior",
    "mid",
    "senior",
    "lead",
    "manager",
    "executive",
    "unknown",
]


def _cap(limit: int) -> BeforeValidator:
    """Keep at most `limit` list items.

    Limits are also stated in the prompt; truncating here keeps validation
    from failing on model servers that don't enforce them.
    """

    def validator(value):
        if isinstance(value, list):
            return value[:limit]
        return value

    return BeforeValidator(validator)


class SkillEvidence(BaseModel):
    source_type: Literal[
        "work_experience",
        "project",
        "skills_section",
        "certification",
        "education",
    ]
    text: str = Field(min_length=1)


class CandidateSkill(BaseModel):
    name: str = Field(min_length=1)
    normalized_name: str = Field(min_length=1)
    evidence: Annotated[list[SkillEvidence], _cap(2)] = Field(default_factory=list)


class CandidateProfile(BaseModel):
    primary_role: str | None = None

    # Category predicted from the resume's actual content.
    category: ResumeCategory | None = None

    role_evidence: Annotated[list[str], _cap(3)] = Field(default_factory=list)

    seniority: Seniority = "unknown"

    domains: Annotated[list[str], _cap(5)] = Field(default_factory=list)
    skills: Annotated[list[CandidateSkill], _cap(40)] = Field(default_factory=list)


class ResumeUploadResponse(BaseModel):
    id: UUID
    name: str
    url: str
    status: str


class WorkExperience(BaseModel):
    company: str | None = None
    designation: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    responsibilities: Annotated[list[str], _cap(5)] = Field(default_factory=list)


class Education(BaseModel):
    institution: str | None = None
    degree: str | None = None
    field_of_study: str | None = None
    graduation_year: str | None = None


class ResumeExtraction(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    summary: str | None = None
    total_experience: str | None = None

    # Retained for compatibility with existing consumers.
    skills: Annotated[list[str], _cap(40)] = Field(default_factory=list)

    work_experience: list[WorkExperience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)

    candidate_profile: CandidateProfile

    @field_validator(
        "full_name",
        "email",
        "phone",
        "location",
        "summary",
        "total_experience",
        mode="before",
    )
    @classmethod
    def normalize_null_strings(cls, value):
        if isinstance(value, str) and value.strip().lower() in {
            "null",
            "none",
            "n/a",
            "not available",
            "not mentioned",
            "",
        }:
            return None
        return value


class ResumeExtractionRequest(BaseModel):
    resume_id: UUID = Field(default_factory=uuid7)
    document_text: str = Field(min_length=1, max_length=60000)


class ResumeSummary(BaseModel):
    """Lightweight resume row for lists (no extracted text)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    content_type: str
    file_size: int
    status: str
    retry_count: int
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    full_name: str | None = None
    primary_role: str | None = None
    category: str | None = None
    seniority: str | None = None
    total_experience_years: float | None = None
    location: str | None = None


class ResumePage(BaseModel):
    total: int
    offset: int
    limit: int
    items: list[ResumeSummary]


class ResumeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    object_name: str
    content_type: str
    file_size: int
    status: str
    extracted_text: str | None = None
    extraction_result: dict | None = None
    retry_count: int
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class ResumeStats(BaseModel):
    total: int
    completed: int
    processing: int
    failed: int
    by_status: dict[str, int]
    by_category: dict[str, int]
