
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


ProviderStatus = Literal["completed", "partial", "failed", "skipped"]


@dataclass(frozen=True)
class SourceEvidence:
    url: str
    title: str | None
    content: str
    retrieved_at: datetime
    metadata: dict[str, str | int | float | bool | None] = field(
        default_factory=dict,
    )


@dataclass(frozen=True)
class SourceResult:
    source_type: str
    url: str
    status: ProviderStatus
    evidence: list[SourceEvidence] = field(default_factory=list)
    error: str | None = None


class ResearchProvider(ABC):
    source_type: str

    @abstractmethod
    async def fetch(self, url: str) -> SourceResult:
        """Retrieve permitted public information from a source URL."""
        raise NotImplementedError
