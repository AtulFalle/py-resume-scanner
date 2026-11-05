from datetime import datetime
from uuid import UUID, uuid7

from pydantic import BaseModel, ConfigDict, Field


from uuid import UUID

from pydantic import BaseModel, Field


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
    skills: list[str] = Field(default_factory=list)
    work_experience: list[WorkExperience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)


class ResumeExtractionRequest(BaseModel):
    resume_id: UUID = Field(default_factory=uuid7)
    document_text: str = Field(min_length=1, max_length=60000)

class ResumeResponse(BaseModel):
    # This configuration is required in Pydantic v2 to automatically 
    # convert your SQLAlchemy attributes into JSON fields.
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


