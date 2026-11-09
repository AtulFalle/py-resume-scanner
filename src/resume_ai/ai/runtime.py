import logging
import time

import httpx

from resume_ai.ai.registry import EmbeddingModelConfig, ModelConfig
from resume_ai.core.config import settings

logger = logging.getLogger(__name__)


class LLMRuntime:
    def __init__(self) -> None:
        self._generation_client: httpx.AsyncClient | None = None
        self._embedding_client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if self._generation_client is not None:
            return

        limits = httpx.Limits(
            max_connections=10,
            max_keepalive_connections=5,
            keepalive_expiry=1500,
        )
        logger.info(
            "LLM runtime started",
            extra={"generation_timeout": settings.ai_llm_timeout},
        )

        self._generation_client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                settings.ai_llm_timeout,
                connect=5.0,
                pool=5.0,
            ),
            limits=limits,
        )

        self._embedding_client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                settings.ai_embedding_timeout,
                connect=5.0,
                pool=5.0,
            ),
            limits=limits,
        )

        logger.info("LLM runtime initialized")

    async def close(self) -> None:
        if self._generation_client is not None:
            await self._generation_client.aclose()
            self._generation_client = None

        if self._embedding_client is not None:
            await self._embedding_client.aclose()
            self._embedding_client = None

        logger.info("LLM runtime closed")

    def _get_generation_client(self) -> httpx.AsyncClient:
        if self._generation_client is None:
            raise RuntimeError("LLM runtime has not been started")

        return self._generation_client

    def _get_embedding_client(self) -> httpx.AsyncClient:
        if self._embedding_client is None:
            raise RuntimeError("LLM runtime has not been started")

        return self._embedding_client

    async def generate(
        self,
        model: ModelConfig,
        messages: list[dict[str, str]],
        response_schema: dict | None = None,
    ) -> str:
        payload = {
            "model": model.name,
            "messages": messages,
            "temperature": model.temperature,
            "max_tokens": model.max_tokens,
            "chat_template_kwargs": {
                "enable_thinking": False,
            },
        }

        if response_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "schema": response_schema,
                },
            }

        client = self._get_generation_client()
        started_at = time.perf_counter()

        try:
            response = await client.post(
                f"{model.base_url}/chat/completions",
                json=payload,
            )
            response.raise_for_status()

            result = response.json()
            choice = result["choices"][0]
            message = choice.get("message", {})
            content = message.get("content")

            if isinstance(content, list):
                content = "".join(
                    item.get("text", "") for item in content if isinstance(item, dict)
                )

            if not content:
                raise RuntimeError(
                    "LLM returned empty content. "
                    f"Finish reason: {choice.get('finish_reason')}. "
                    f"Usage: {result.get('usage')}"
                )

            usage = result.get("usage", {})

            logger.info(
                "LLM generation completed model=%s duration_ms=%.2f "
                "prompt_tokens=%s completion_tokens=%s",
                model.name,
                (time.perf_counter() - started_at) * 1000,
                usage.get("prompt_tokens"),
                usage.get("completion_tokens"),
            )

            return content

        except httpx.TimeoutException:
            logger.exception(
                "LLM generation timed out model=%s duration_ms=%.2f",
                model.name,
                (time.perf_counter() - started_at) * 1000,
            )
            raise

        except httpx.HTTPStatusError as error:
            logger.error(
                "LLM HTTP error model=%s status=%s duration_ms=%.2f",
                model.name,
                error.response.status_code,
                (time.perf_counter() - started_at) * 1000,
            )
            raise

        except httpx.RequestError:
            logger.exception(
                "LLM connection error model=%s duration_ms=%.2f",
                model.name,
                (time.perf_counter() - started_at) * 1000,
            )
            raise

        except Exception:
            logger.exception("LLM generation failed model=%s", model.name)
            raise

    async def embed(
        self,
        model: EmbeddingModelConfig,
        texts: list[str],
    ) -> list[list[float]]:
        if not texts:
            return []

        payload = {
            "model": model.name,
            "input": texts,
            "encoding_format": "float",
        }

        client = self._get_embedding_client()
        started_at = time.perf_counter()

        try:
            response = await client.post(
                f"{model.base_url}/embeddings",
                json=payload,
            )
            response.raise_for_status()

            result = response.json()
            data = sorted(
                result["data"],
                key=lambda item: item["index"],
            )
            vectors = [item["embedding"] for item in data]

            if len(vectors) != len(texts):
                raise RuntimeError("Embedding response count does not match input count")

            for vector in vectors:
                if len(vector) != model.dimensions:
                    raise RuntimeError(
                        f"Expected {model.dimensions} dimensions, received {len(vector)}"
                    )

            logger.info(
                "Embedding completed model=%s inputs=%d duration_ms=%.2f",
                model.name,
                len(texts),
                (time.perf_counter() - started_at) * 1000,
            )

            return vectors

        except httpx.TimeoutException:
            logger.exception(
                "Embedding timed out model=%s inputs=%d duration_ms=%.2f",
                model.name,
                len(texts),
                (time.perf_counter() - started_at) * 1000,
            )
            raise

        except httpx.HTTPStatusError as error:
            logger.error(
                "Embedding HTTP error model=%s status=%s",
                model.name,
                error.response.status_code,
            )
            raise

        except httpx.RequestError:
            logger.exception(
                "Embedding connection error model=%s",
                model.name,
            )
            raise

        except Exception:
            logger.exception("Embedding failed model=%s", model.name)
            raise


llm_runtime = LLMRuntime()
