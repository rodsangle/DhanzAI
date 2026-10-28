"""URL safety checks for server-side fetching (SSRF protection)."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from dhanz_knowledge.types import FetchError

Resolver = Callable[[str], Awaitable[list[str]]]

ALLOWED_PORTS = {None, 80, 443}


async def system_resolver(host: str) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return sorted({info[4][0] for info in infos})


def _is_public(ip: str) -> bool:
    addr = ipaddress.ip_address(ip.split("%")[0])
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


async def check_url(url: str, resolver: Resolver = system_resolver, *, allow_private: bool = False) -> str:
    """Validate that `url` is an http(s) URL on a standard port that resolves only to public addresses.

    Returns the normalised URL. Raises FetchError otherwise. Every redirect hop must be checked
    again by the caller.
    """
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        raise FetchError(url, "invalid URL") from None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise FetchError(url, "only http and https links can be read")
    if parts.username or parts.password:
        raise FetchError(url, "links with embedded credentials are not allowed")
    try:
        port = parts.port
    except ValueError:
        raise FetchError(url, "invalid port") from None
    if port not in ALLOWED_PORTS:
        raise FetchError(url, "only standard web ports (80/443) are allowed")
    if not allow_private:
        host = parts.hostname
        try:
            addrs = [host] if _looks_like_ip(host) else await resolver(host)
        except OSError:
            raise FetchError(url, "the site's address could not be resolved") from None
        if not addrs or not all(_is_public(a) for a in addrs):
            raise FetchError(url, "private or internal network addresses cannot be accessed")
    return parts.geturl()


def _looks_like_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False
