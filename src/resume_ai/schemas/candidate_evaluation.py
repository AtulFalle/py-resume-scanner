from typing import Literal

from pydantic import BaseModel, Field


class SkillAssessment(BaseModel):
    requirement: str
    status: Literal["met", "partial", "missing"]
    candidate_evidence: str


class CandidateEvaluation(BaseModel):
    match_score: int = Field(ge=0, le=100)
    summary: str
    skills: list[SkillAssessment]
    relevant_experience: str
    strengths: list[str]
    gaps: list[str]
    evidence: list[str]
