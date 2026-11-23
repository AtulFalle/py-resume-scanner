from pydantic import BaseModel, Field, field_validator

from resume_ai.schemas.resume_schema import ResumeCategory


class RetrievedChunk(BaseModel):
    resume_id: str
    chunk_index: int
    text: str
    score: float


class CandidateMatch(BaseModel):
    resume_id: str
    score: float
    matched_chunks: list[RetrievedChunk] = Field(default_factory=list)


class SearchRequirements(BaseModel):
    """Structured interpretation of a recruiter's query.

    Produced by the query-parsing model, then optionally overridden by the
    filters the recruiter set explicitly in the UI.
    """

    role: str | None = None
    categories: list[ResumeCategory] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    min_years: float | None = Field(default=None, ge=0, le=60)
    max_years: float | None = Field(default=None, ge=0, le=60)
    location: str | None = None
    search_text: str = ""

    @field_validator("required_skills", "preferred_skills", mode="before")
    @classmethod
    def clean_skills(cls, value):
        if not isinstance(value, list):
            return value

        cleaned: list[str] = []
        seen: set[str] = set()

        for item in value:
            if not isinstance(item, str):
                continue
            skill = " ".join(item.split()).strip()
            if skill and skill.lower() not in seen:
                seen.add(skill.lower())
                cleaned.append(skill)

        return cleaned[:8]

    @field_validator("categories", mode="before")
    @classmethod
    def limit_categories(cls, value):
        if isinstance(value, list):
            return value[:3]
        return value


class CandidateSearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=20000)

    # Max candidates sent to the LLM for evaluation (the slow step).
    # Defaults to SEARCH_SHORTLIST_SIZE.
    limit: int | None = Field(default=None, ge=1, le=25)

    # Candidates scoring below this are dropped. Defaults to SEARCH_MIN_MATCH_SCORE.
    min_score: int | None = Field(default=None, ge=0, le=100)

    # Explicit recruiter filters. When set, they replace what was parsed from the query.
    required_skills: list[str] | None = None
    categories: list[ResumeCategory] | None = None
    min_years: float | None = Field(default=None, ge=0, le=60)
    include_unknown_experience: bool = True


class MatchedChunkResponse(BaseModel):
    chunk_index: int
    text: str
    score: float


class SkillAssessmentResponse(BaseModel):
    requirement: str
    required: bool = False
    status: str
    candidate_evidence: str


class CandidateLink(BaseModel):
    url: str
    source_type: str


class CandidateSearchResult(BaseModel):
    resume_id: str
    filename: str

    full_name: str | None = None
    primary_role: str | None = None
    category: str | None = None
    seniority: str | None = None
    location: str | None = None
    total_experience_years: float | None = None
    experience_source: str | None = None
    links: list[CandidateLink] = Field(default_factory=list)

    semantic_score: float
    match_score: int
    profession_match: bool = True
    summary: str
    skills: list[SkillAssessmentResponse]
    relevant_experience: str
    strengths: list[str]
    gaps: list[str]
    evidence: list[str]
    matched_chunks: list[MatchedChunkResponse]


class SearchStats(BaseModel):
    # Resumes that passed the hard filters (skills / years / category).
    passed_filters: int | None = None
    # Distinct candidates found by vector search.
    retrieved: int = 0
    # Candidates evaluated by the LLM.
    evaluated: int = 0
    # Evaluated candidates removed for scoring below min_score.
    below_threshold: int = 0
    min_score: int = 0


class CandidateSearchResponse(BaseModel):
    total: int
    requirements: SearchRequirements
    stats: SearchStats
    message: str | None = None
    candidates: list[CandidateSearchResult]
