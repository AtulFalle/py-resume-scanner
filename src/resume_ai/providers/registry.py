
from resume_ai.research.providers.base import ResearchProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ResearchProvider] = {}

    def register(self, provider: ResearchProvider) -> None:
        source_type = provider.source_type.lower().strip()

        if not source_type:
            raise ValueError("Provider source_type cannot be empty")

        if source_type in self._providers:
            raise ValueError(f"Provider already registered: {source_type}")

        self._providers[source_type] = provider

    def get(self, source_type: str) -> ResearchProvider | None:
        return self._providers.get(source_type.lower().strip())

    def supported_sources(self) -> list[str]:
        return sorted(self._providers.keys())


provider_registry = ProviderRegistry()
