from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field


def _cap(limit: int) -> BeforeValidator:
    def validator(value):
        if isinstance(value, list):
            return value[:limit]
        return value

    return BeforeValidator(validator)


class SkillAssessment(BaseModel):
    requirement: str
    # True for requirements the recruiter marked as essential.
    required: bool = False
    status: Literal["met", "partial", "missing"]
    candidate_evidence: str


class CandidateEvaluation(BaseModel):
    """LLM evaluation of one candidate.

    Field order matters: grammar-constrained servers (llama.cpp) generate
    properties in schema order, so the model writes its assessment first and
    only then commits to a score.
    """

    profession_match: bool = Field(
        description=(
            "True only if the candidate works in the same profession/role family "
            "as the job (e.g. a frontend developer for a frontend developer job)."
        )
    )
    skills: Annotated[list[SkillAssessment], _cap(10)]
    relevant_experience: str
    strengths: Annotated[list[str], _cap(4)]
    gaps: Annotated[list[str], _cap(4)]
    evidence: Annotated[list[str], _cap(4)]
    summary: str
    match_score: int = Field(ge=0, le=100)
