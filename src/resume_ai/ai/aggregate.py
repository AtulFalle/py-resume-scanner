
from collections import defaultdict

from resume_ai.schemas.search import CandidateMatch, RetrievedChunk


class CandidateAggregation:
    def execute(
        self,
        chunks: list[RetrievedChunk],
        max_chunks_per_candidate: int = 3,
    ) -> list[CandidateMatch]:
        grouped: dict[str, list[RetrievedChunk]] = defaultdict(list)

        for chunk in chunks:
            grouped[chunk.resume_id].append(chunk)

        candidates = []

        for resume_id, candidate_chunks in grouped.items():
            ranked_chunks = sorted(
                candidate_chunks,
                key=lambda chunk: chunk.score,
                reverse=True,
            )

            matched_chunks = ranked_chunks[:max_chunks_per_candidate]

            candidates.append(
                CandidateMatch(
                    resume_id=resume_id,
                    score=matched_chunks[0].score,
                    matched_chunks=matched_chunks,
                )
            )

        return sorted(
            candidates,
            key=lambda candidate: candidate.score,
            reverse=True,
        )


candidate_aggregation = CandidateAggregation()
