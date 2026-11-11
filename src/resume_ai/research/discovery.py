
import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

TRAILING_PUNCTUATION = ".,;:!?)]}"

@dataclass(frozen=True)
class DiscoveredURL:
    original_url: str
    normalized_url: str
    source_type: str


def classify_source(hostname: str) -> str:
    hostname = hostname.lower().removeprefix("www.")

    if hostname == "github.com":
        return "github"

    if hostname == "linkedin.com":
        return "linkedin"

    return "website"


def normalize_url(url: str) -> str | None:
    url = url.rstrip(TRAILING_PUNCTUATION)

    try:
        parsed = urlsplit(url)

        if parsed.scheme.lower() not in {"http", "https"}:
            return None

        if not parsed.hostname:
            return None

        if parsed.username or parsed.password:
            return None

        # Accessing port validates its syntax and range.
        _ = parsed.port

        return urlunsplit(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                parsed.path,
                parsed.query,
                "",
            )
        )

    except ValueError:
        return None


def discover_urls(document_text: str) -> list[DiscoveredURL]:
    discovered: list[DiscoveredURL] = []
    seen: set[str] = set()

    for match in URL_PATTERN.findall(document_text):
        original_url = match.rstrip(TRAILING_PUNCTUATION)
        normalized_url = normalize_url(original_url)

        if normalized_url is None or normalized_url in seen:
            continue

        hostname = urlsplit(normalized_url).hostname

        if hostname is None:
            continue

        seen.add(normalized_url)

        discovered.append(
            DiscoveredURL(
                original_url=original_url,
                normalized_url=normalized_url,
                source_type=classify_source(hostname),
            )
        )

    return discovered
