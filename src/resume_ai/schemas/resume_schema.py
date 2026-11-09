
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid7

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    evidence: list[SkillEvidence] = Field(default_factory=list)


class CandidateProfile(BaseModel):
    primary_role: str | None = None

    # Category predicted from the resume's actual content.
    category: ResumeCategory | None = None

    # Preserve the dataset's original label for evaluation.
    dataset_category: ResumeCategory | None = None

    role_evidence: list[str] = Field(default_factory=list)

    seniority: Literal[
        "entry",
        "junior",
        "mid",
        "senior",
        "lead",
        "manager",
        "executive",
        "unknown",
    ] = "unknown"

    domains: list[str] = Field(default_factory=list)
    skills: list[CandidateSkill] = Field(default_factory=list)

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
    responsibilities: list[str] = Field(default_factory=list)


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
    skills: list[str] = Field(default_factory=list)

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
            "null", "none", "n/a", "not available", ""
        }:
            return None
        return value


class ResumeExtractionRequest(BaseModel):
    resume_id: UUID = Field(default_factory=uuid7)
    document_text: str = Field(min_length=1, max_length=60000)


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
