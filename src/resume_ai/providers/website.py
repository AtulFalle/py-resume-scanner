import asyncio
import ipaddress
import logging
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from resume_ai.core.config import settings
from resume_ai.providers.base import ResearchProvider, SourceEvidence, SourceResult

logger = logging.getLogger(__name__)

USER_AGENT = "ResumeScreenerBot/1.0"
MAX_REDIRECTS = 3
MAX_BYTES = 1_000_000
MAX_TEXT_CHARS = 4000
SKIP_TAGS = {"script", "style", "noscript", "svg", "template"}
VOID_TAGS = {"meta", "link", "br", "img", "input", "hr", "area", "base", "col", "source"}
REDIRECT_CODES = {301, 302, 303, 307, 308}


class UnsafeURLError(ValueError):
    """Raised when a URL is not allowed to be fetched."""


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.description: str | None = None
        self.text_parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "meta":
            values = {k.lower(): v for k, v in attrs if v is not None}
            if values.get("name", "").lower() == "description" and self.description is None:
                self.description = values.get("content")
            return
        if tag in VOID_TAGS:
            return
        if tag in SKIP_TAGS:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "meta":
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        elif self._skip_depth == 0:
            self.text_parts.append(data)


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _is_public_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
        or not address.is_global
    )


async def _validate_url(url: str) -> None:
    parsed = urlsplit(url)

    if parsed.scheme not in {"http", "https"}:
        raise UnsafeURLError("Only http and https URLs are allowed")

    hostname = parsed.hostname
    if not hostname:
        raise UnsafeURLError("URL has no host")

    try:
        port = parsed.port
    except ValueError as error:
        raise UnsafeURLError("Invalid URL port") from error

    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            hostname,
            port or (443 if parsed.scheme == "https" else 80),
            type=0,
        )
    except OSError as error:
        raise UnsafeURLError(f"Could not resolve host: {hostname}") from error

    if not infos:
        raise UnsafeURLError(f"Could not resolve host: {hostname}")

    for info in infos:
        raw_address = info[4][0].split("%", 1)[0]
        try:
            address = ipaddress.ip_address(raw_address)
        except ValueError as error:
            raise UnsafeURLError("Host resolved to an invalid address") from error
        if not _is_public_ip(address):
            raise UnsafeURLError("URL resolves to a non-public address")


async def _safe_fetch(
    client: httpx.AsyncClient,
    url: str,
) -> tuple[httpx.Response, bytes, str]:
    """GET a URL with manual redirects, per-hop validation and a size cap.

    Returns (response, body, final_url). The body is truncated at MAX_BYTES.
    """
    current = url

    for _ in range(MAX_REDIRECTS + 1):
        await _validate_url(current)

        async with client.stream("GET", current) as response:
            if response.status_code in REDIRECT_CODES:
                location = response.headers.get("location")
                if not location:
                    raise UnsafeURLError("Redirect without a Location header")
                current = urljoin(current, location)
                continue

            content_type = response.headers.get("content-type", "")
            body = b""
            if response.status_code < 400 and (
                "text/html" in content_type.lower() or current.endswith("/robots.txt")
            ):
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    chunks.append(chunk)
                    size += len(chunk)
                    if size >= MAX_BYTES:
                        break
                body = b"".join(chunks)[:MAX_BYTES]
            return response, body, current

    raise UnsafeURLError(f"Too many redirects (more than {MAX_REDIRECTS})")


class WebsiteProvider(ResearchProvider):
    source_type = "website"

    async def fetch(self, url: str) -> SourceResult:
        try:
            return await self._fetch(url)
        except UnsafeURLError as error:
            return self._result(url, "failed", f"Blocked URL: {error}")
        except httpx.HTTPError as error:
            logger.warning("Website fetch failed for %s: %s", url, error)
            return self._result(url, "failed", f"Request failed: {error or type(error).__name__}")
        except Exception as error:
            logger.exception("Unexpected website fetch error for %s", url)
            return self._result(url, "failed", f"Unexpected error: {error}")

    async def _fetch(self, url: str) -> SourceResult:
        timeout = httpx.Timeout(settings.research_http_timeout, connect=5.0)

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml;q=0.9",
            },
        ) as client:
            await _validate_url(url)

            if not await self._allowed_by_robots(client, url):
                return self._result(url, "skipped", "Fetching is disallowed by robots.txt")

            response, body, final_url = await _safe_fetch(client, url)

        if response.status_code >= 400:
            return self._result(url, "failed", f"Website returned HTTP {response.status_code}")

        content_type = response.headers.get("content-type", "").lower()
        if "text/html" not in content_type:
            return self._result(
                url,
                "failed",
                f"Unsupported content type: {content_type or 'unknown'}",
            )

        encoding = response.charset_encoding or "utf-8"
        try:
            html = body.decode(encoding, errors="replace")
        except LookupError:
            html = body.decode("utf-8", errors="replace")

        extractor = _TextExtractor()
        extractor.feed(html)
        extractor.close()

        title = _collapse(" ".join(extractor.title_parts)) or None
        description = _collapse(extractor.description) if extractor.description else None
        text = _collapse(" ".join(extractor.text_parts))[:MAX_TEXT_CHARS]

        evidence = SourceEvidence(
            url=final_url,
            title=title,
            content=text,
            retrieved_at=datetime.now(UTC),
            metadata={
                "description": description,
                "status_code": response.status_code,
                "truncated": len(body) >= MAX_BYTES,
            },
        )
        return SourceResult(
            source_type=self.source_type,
            url=url,
            status="completed",
            evidence=[evidence],
        )

    async def _allowed_by_robots(self, client: httpx.AsyncClient, url: str) -> bool:
        parsed = urlsplit(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

        try:
            response, body, _ = await _safe_fetch(client, robots_url)
        except (UnsafeURLError, httpx.HTTPError):
            # An unreachable robots.txt is treated like a missing one.
            return True

        if 400 <= response.status_code < 500:
            return True
        if response.status_code >= 500:
            return True

        parser = RobotFileParser()
        parser.parse(body.decode("utf-8", errors="replace").splitlines())
        return parser.can_fetch(USER_AGENT, url)

    def _result(self, url: str, status: str, error: str) -> SourceResult:
        return SourceResult(
            source_type=self.source_type,
            url=url,
            status=status,  # type: ignore[arg-type]
            error=error,
        )
