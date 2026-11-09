from resume_ai.schemas.search import RetrievedChunk
from resume_ai.storage.qdrant import qdrant_storage


class CandidateRetrieval:
    async def execute(
        self,
        query_vector: list[float],
        limit: int = 50,
    ) -> list[RetrievedChunk]:
        points = await qdrant_storage.search_chunks(
            vector=query_vector,
            limit=limit,
        )

        chunks = []

        for point in points:
            payload = point.payload or {}

            resume_id = payload.get("resume_id")
            text = payload.get("text")

            if not resume_id or not text:
                continue

            chunks.append(
                RetrievedChunk(
                    resume_id=resume_id,
                    chunk_index=payload.get("chunk_index", 0),
                    text=text,
                    score=point.score,
                )
            )

        return chunks


candidate_retrieval = CandidateRetrieval()
