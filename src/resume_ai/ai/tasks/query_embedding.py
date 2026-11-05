
from resume_ai.ai.registry import model_registry
from resume_ai.ai.runtime import llm_runtime


class QueryEmbedding:
    async def execute(self, query: str) -> list[float]:
        if not query.strip():
            raise ValueError("Search query cannot be empty")

        model = model_registry.get_embedding("resume_embedding")

        vectors = await llm_runtime.embed(
            model=model,
            texts=[f"search_query: {query.strip()}"],
        )

        return vectors[0]


query_embedding = QueryEmbedding()
