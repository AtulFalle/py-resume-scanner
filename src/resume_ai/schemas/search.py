
from pydantic import BaseModel, Field

class RetrievedChunk(BaseModel):
    resume_id: str
    chunk_index: int
    text: str
    score: float


class CandidateMatch(BaseModel):
    resume_id: str
    score: float
    matched_chunks: list[RetrievedChunk] = Field(default_factory=list)


class CandidateSearchRequest(BaseModel):
    query: str = Field(min_length=10, max_length=20000)
    limit: int = Field(default=50, ge=1, le=100)


class MatchedChunkResponse(BaseModel):
    chunk_index: int
    text: str
    score: float


class CandidateSearchResult(BaseModel):
    resume_id: str
    filename: str
    semantic_score: float
    match_score: int
    summary: str
    skills: list[SkillAssessmentResponse]
    relevant_experience: str
    strengths: list[str]
    gaps: list[str]
    evidence: list[str]
    matched_chunks: list[MatchedChunkResponse]


class CandidateSearchResponse(BaseModel):
    total: int
    candidates: list[CandidateSearchResult]



class SkillAssessmentResponse(BaseModel):
    requirement: str
    status: str
    candidate_evidence: str
