import re
from collections.abc import Iterable
from dataclasses import dataclass
from io import BytesIO
from urllib.parse import urlsplit, urlunsplit

from pypdf import PdfReader

URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

# Resumes often write profile links without a scheme: "linkedin.com/in/jane".
BARE_PROFILE_PATTERN = re.compile(
    r"(?<![\w/@.])(?:www\.)?(?:[a-z]{2,3}\.)?(linkedin\.com|github\.com)/[^\s<>\"'|,;]+",
    re.IGNORECASE,
)

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

    if hostname == "linkedin.com" or hostname.endswith(".linkedin.com"):
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
                parsed.path.rstrip("/") or "/",
                parsed.query,
                "",
            )
        )

    except ValueError:
        return None


def extract_pdf_link_targets(file_content: bytes) -> list[str]:
    """Return URLs behind clickable links in a PDF.

    `extract_text()` only returns the visible text, so a link shown as
    "LinkedIn" would otherwise lose its URL.
    """
    urls: list[str] = []

    try:
        reader = PdfReader(BytesIO(file_content))

        for page in reader.pages:
            annotations = page.get("/Annots") or []

            for annotation_ref in annotations:
                annotation = annotation_ref.get_object()

                if annotation.get("/Subtype") != "/Link":
                    continue

                action = annotation.get("/A")
                if action is None:
                    continue

                uri = action.get_object().get("/URI")
                if isinstance(uri, bytes):
                    uri = uri.decode("utf-8", errors="ignore")
                if isinstance(uri, str) and uri.lower().startswith(("http://", "https://")):
                    urls.append(uri.strip())

    except Exception:
        # Link extraction is best-effort; never fail processing because of it.
        return urls

    return urls


def _candidates_from_text(document_text: str) -> list[str]:
    found = [match for match in URL_PATTERN.findall(document_text)]

    for match in BARE_PROFILE_PATTERN.finditer(document_text):
        found.append("https://" + match.group(0))

    return found


def discover_urls(
    document_text: str,
    extra_urls: Iterable[str] = (),
) -> list[DiscoveredURL]:
    discovered: list[DiscoveredURL] = []
    seen: set[str] = set()

    for match in [*extra_urls, *_candidates_from_text(document_text)]:
        original_url = match.rstrip(TRAILING_PUNCTUATION)
        normalized_url = normalize_url(original_url)

        if normalized_url is None:
            continue

        # Treat www/non-www and http/https as the same link.
        dedupe_key = normalized_url.split("://", 1)[1].removeprefix("www.")
        if dedupe_key in seen:
            continue

        hostname = urlsplit(normalized_url).hostname

        if hostname is None:
            continue

        seen.add(dedupe_key)

        discovered.append(
            DiscoveredURL(
                original_url=original_url,
                normalized_url=normalized_url,
                source_type=classify_source(hostname),
            )
        )

    return discovered
