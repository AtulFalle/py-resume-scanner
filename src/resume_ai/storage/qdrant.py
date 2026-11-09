from uuid import NAMESPACE_URL, uuid5

from qdrant_client import AsyncQdrantClient, models

from resume_ai.core.config import settings


class QdrantStorage:
    COLLECTION_NAME = "resumes"

    def __init__(self) -> None:
        self.client = AsyncQdrantClient(url=settings.qdrant_url)

    async def ensure_collection(self) -> None:
        exists = await self.client.collection_exists(self.COLLECTION_NAME)

        if not exists:
            await self.client.create_collection(
                collection_name=self.COLLECTION_NAME,
                vectors_config=models.VectorParams(
                    size=settings.ai_embedding_dimensions,
                    distance=models.Distance.COSINE,
                ),
            )

    async def upsert_chunks(
        self,
        resume_id: str,
        chunks: list[str],
        vectors: list[list[float]],
    ) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("Chunk and vector counts do not match")

        points = []

        for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=False)):
            if len(vector) != settings.ai_embedding_dimensions:
                raise ValueError("Unexpected embedding dimensions")

            point_id = str(
                uuid5(
                    NAMESPACE_URL,
                    f"resume:{resume_id}:chunk:{index}",
                )
            )

            points.append(
                models.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "resume_id": resume_id,
                        "chunk_index": index,
                        "text": chunk,
                    },
                )
            )

        # Remove old chunks when reprocessing a resume.
        await self.client.delete(
            collection_name=self.COLLECTION_NAME,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="resume_id",
                            match=models.MatchValue(value=resume_id),
                        )
                    ]
                )
            ),
            wait=True,
        )

        if points:
            await self.client.upsert(
                collection_name=self.COLLECTION_NAME,
                points=points,
                wait=True,
            )

    async def close(self) -> None:
        await self.client.close()

    async def search_chunks(
        self,
        vector: list[float],
        limit: int = 50,
        score_threshold: float | None = None,
    ) -> list[models.ScoredPoint]:
        if len(vector) != settings.ai_embedding_dimensions:
            raise ValueError("Unexpected query embedding dimensions")

        result = await self.client.query_points(
            collection_name=self.COLLECTION_NAME,
            query=vector,
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
        )

        return result.points


qdrant_storage = QdrantStorage()
