
import httpx

from resume_ai.ai.registry import EmbeddingModelConfig, ModelConfig
from resume_ai.core.config import settings


class LLMRuntime:
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

        async with httpx.AsyncClient(
            timeout=settings.ai_llm_timeout,
        ) as client:
            response = await client.post(
                f"{model.base_url}/chat/completions",
                json=payload,
            )

        if not response.is_success:
            raise RuntimeError(
                f"LLM request failed: HTTP {response.status_code} "
                f"- {response.text}"
            )

        result = response.json()
        choice = result["choices"][0]
        message = choice.get("message", {})
        content = message.get("content")

        if isinstance(content, list):
            content = "".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict)
            )

        if not content:
            raise RuntimeError(
                "LLM returned empty content. "
                f"Finish reason: {choice.get('finish_reason')}. "
                f"Usage: {result.get('usage')}"
            )

        return content

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

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{model.base_url}/embeddings",
                json=payload,
            )

        if not response.is_success:
            raise RuntimeError(
                f"Embedding request failed: HTTP {response.status_code} "
                f"- {response.text}"
            )

        result = response.json()
        data = sorted(
            result["data"],
            key=lambda item: item["index"],
        )
        vectors = [item["embedding"] for item in data]

        if len(vectors) != len(texts):
            raise RuntimeError(
                "Embedding response count does not match input count"
            )

        for vector in vectors:
            if len(vector) != model.dimensions:
                raise RuntimeError(
                    f"Expected {model.dimensions} dimensions, "
                    f"received {len(vector)}"
                )

        return vectors


llm_runtime = LLMRuntime()
