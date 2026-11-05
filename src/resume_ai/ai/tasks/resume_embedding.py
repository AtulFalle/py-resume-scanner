
from resume_ai.ai.chunking import text_chunker
from resume_ai.ai.registry import model_registry
from resume_ai.ai.runtime import llm_runtime


class ResumeEmbeddingTask:
    async def execute(
        self,
        document_text: str,
    ) -> tuple[list[str], list[list[float]]]:

        chunks = text_chunker.split(document_text)

        if not chunks:
            raise ValueError("Cannot embed empty resume")

        model = model_registry.get_embedding("resume_embedding")

        vectors = await llm_runtime.embed(
            model=model,
            texts=[
                f"search_document: {chunk}"
                for chunk in chunks
            ],
        )

        return chunks, vectors


resume_embedding_task = ResumeEmbeddingTask()
