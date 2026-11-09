from resume_ai.ai.aggregate import candidate_aggregation
from resume_ai.ai.retrival import candidate_retrieval
from resume_ai.ai.tasks.query_embedding import query_embedding
from resume_ai.schemas.search import CandidateMatch


class CandidateSearch:
    async def execute(
        self,
        query: str,
        retrieval_limit: int = 50,
    ) -> list[CandidateMatch]:
        if not query.strip():
            raise ValueError("Search query cannot be empty")

        # Convert the job description into a query vector.
        vector = await query_embedding.execute(query)

        # Retrieve matching resume chunks.
        chunks = await candidate_retrieval.execute(
            query_vector=vector,
            limit=retrieval_limit,
        )

        if not chunks:
            return []

        # Group matching chunks into candidate-level results.
        return candidate_aggregation.execute(chunks)


candidate_search = CandidateSearch()
