"""Polite, safe web page fetching.

* Honours robots.txt (RFC 9309) for our user agent, cached per host.
* Spaces out requests to the same host.
* Never sends cookies or credentials and never tries to get around paywalls, logins or
  other access controls: 401/402/403 responses are reported as "not accessible".
* Blocks private/internal addresses on every redirect hop (SSRF protection).
* Caps response size and accepts only HTML and plain text.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from dhanz_knowledge.extract import extract_page
from dhanz_knowledge.safety import Resolver, check_url, system_resolver
from dhanz_knowledge.types import FetchError, Page

DEFAULT_USER_AGENT = "DhanzAI-Research/0.2 (+https://github.com/rodsangle/videotomp3)"
ROBOTS_AGENT = "DhanzAI-Research"
MAX_BYTES = 2_000_000
MAX_REDIRECTS = 5
ROBOTS_TTL_SECONDS = 3600
ACCEPTED_TYPES = ("text/html", "application/xhtml+xml", "text/plain")


class Fetcher:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        resolver: Resolver = system_resolver,
        allow_private: bool = False,
        min_host_interval: float = 1.0,
        timeout: float = 15.0,
    ):
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self.user_agent = user_agent
        self._resolver = resolver
        self._allow_private = allow_private
        self._min_interval = min_host_interval
        self._robots: dict[str, tuple[float, RobotFileParser | None]] = {}
        self._last_hit: dict[str, float] = {}
        self._host_locks: dict[str, asyncio.Lock] = {}

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch(self, url: str) -> Page:
        url = await check_url(url, self._resolver, allow_private=self._allow_private)
        if not await self.allowed_by_robots(url):
            raise FetchError(url, "the site's robots.txt does not allow automated reading of this page")
        response = await self._get(url, accept=",".join(ACCEPTED_TYPES))
        if response.status_code in (401, 402, 403):
            raise FetchError(url, "the page requires a login or subscription, so it was not read")
        if response.status_code == 429:
            raise FetchError(url, "the site asked us to slow down (HTTP 429)")
        if response.status_code >= 400:
            raise FetchError(url, f"the site returned HTTP {response.status_code}")
        ctype = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if ctype and ctype not in ACCEPTED_TYPES:
            raise FetchError(url, f"unsupported content type ({ctype})")
        final_url = str(response.url)
        body = response.text
        page = extract_page(body, final_url, is_html=ctype != "text/plain")
        if len(page.text) < 40:
            raise FetchError(url, "no readable text was found on the page")
        return Page(
            url=page.url,
            title=page.title,
            text=page.text,
            site_name=page.site_name,
            author=page.author,
            published_at=page.published_at,
            retrieved_at=datetime.now(UTC),
            language=page.language,
        )

    async def allowed_by_robots(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        cached = self._robots.get(origin)
        if cached is None or time.monotonic() - cached[0] > ROBOTS_TTL_SECONDS:
            parser = await self._load_robots(origin)
            cached = (time.monotonic(), parser)
            self._robots[origin] = cached
        parser = cached[1]
        if parser is None:  # robots.txt unreachable because of a server error: assume disallowed
            return False
        return parser.can_fetch(ROBOTS_AGENT, url)

    async def _load_robots(self, origin: str) -> RobotFileParser | None:
        parser = RobotFileParser()
        try:
            response = await self._get(f"{origin}/robots.txt", accept="text/plain")
        except FetchError:
            return None
        if response.status_code >= 500:
            return None
        if response.status_code >= 400:
            parser.parse([])  # RFC 9309: unavailable robots.txt (4xx) means no restrictions
        else:
            parser.parse(response.text.splitlines())
        return parser

    async def _get(self, url: str, *, accept: str) -> httpx.Response:
        """GET with manual redirects so every hop is re-validated, plus per-host spacing and a size cap."""
        for _ in range(MAX_REDIRECTS + 1):
            await self._throttle(urlsplit(url).netloc)
            try:
                request = self._client.build_request(
                    "GET", url, headers={"User-Agent": self.user_agent, "Accept": accept}
                )
                response = await self._client.send(request, stream=True, follow_redirects=False)
            except httpx.HTTPError as exc:
                raise FetchError(url, f"network error ({type(exc).__name__})") from exc
            try:
                if response.is_redirect and "location" in response.headers:
                    url = await check_url(
                        urljoin(url, response.headers["location"]), self._resolver, allow_private=self._allow_private
                    )
                    continue
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise FetchError(url, "the page is too large to read")
                    chunks.append(chunk)
                # Body is already decoded; drop transfer headers so httpx doesn't decode it twice.
                headers = {
                    k: v
                    for k, v in response.headers.items()
                    if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")
                }
                return httpx.Response(
                    response.status_code,
                    headers=headers,
                    content=b"".join(chunks),
                    request=response.request,
                )
            finally:
                await response.aclose()
        raise FetchError(url, "too many redirects")

    async def _throttle(self, host: str) -> None:
        lock = self._host_locks.setdefault(host, asyncio.Lock())
        async with lock:
            wait = self._last_hit.get(host, 0) + self._min_interval - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_hit[host] = time.monotonic()
