
from dataclasses import dataclass

from resume_ai.core.config import settings


@dataclass(frozen=True)
class ModelConfig:
    name: str
    base_url: str
    temperature: float = 0.1
    max_tokens: int = 8192


@dataclass(frozen=True)
class EmbeddingModelConfig:
    name: str
    base_url: str
    dimensions: int


class ModelRegistry:
    def __init__(self) -> None:
        self._models: dict[str, ModelConfig] = {
            "resume_extraction": ModelConfig(
                name=settings.ai_resume_extraction_model,
                base_url=settings.ai_llm_base_url,
            ),
        }

        self._embedding_models: dict[str, EmbeddingModelConfig] = {
            "resume_embedding": EmbeddingModelConfig(
                name=settings.ai_embedding_model,
                base_url=settings.ai_embedding_base_url,
                dimensions=settings.ai_embedding_dimensions,
            ),
        }

    def get(self, task: str) -> ModelConfig:
        model = self._models.get(task)

        if model is None:
            raise ValueError(f"No model configured for task: {task}")

        return model

    def get_embedding(self, task: str) -> EmbeddingModelConfig:
        model = self._embedding_models.get(task)

        if model is None:
            raise ValueError(f"No embedding model configured for task: {task}")

        return model


model_registry = ModelRegistry()
