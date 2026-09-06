import ipaddress
import socket
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from ..config import settings
from ..models import EventIn


def timestamp(value: Any, fallback: datetime | None = None) -> datetime:
    if value is None or value == "":
        if fallback is not None:
            return fallback
        raise ValueError("Missing source timestamp")
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value / 1000 if value > 100_000_000_000 else value, UTC)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def validate_url(url: str, allow_hosts: str = "") -> str:
    parsed = urlparse(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Use an HTTP(S) URL without embedded credentials")
    if parsed.hostname in {h.strip() for h in allow_hosts.split(",") if h.strip()}:
        return url
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError(
            "Private destinations require an explicit WATCH_ALLOWED_OUTBOUND_HOSTS entry"
        )
    return url


@dataclass
class Batch:
    events: list[EventIn] = field(default_factory=list)
    raw: list[Any] = field(default_factory=list)
    checkpoint: dict[str, Any] = field(default_factory=dict)
    rejected: int = 0


class Fetcher:
    """Bounded HTTP client; never follow an unvalidated redirect."""

    def __init__(self, transport: httpx.BaseTransport | None = None):
        self.client = httpx.Client(
            timeout=45,
            follow_redirects=False,
            transport=transport,
            headers={"User-Agent": settings().user_agent},
        )

    def close(self) -> None:
        self.client.close()

    def get(self, url: str, params: dict[str, Any] | None = None) -> httpx.Response:
        validate_url(url, settings().allowed_outbound_hosts)
        # Streaming bounds compressed response expansion too.
        with self.client.stream("GET", url, params=params) as response:
            response.raise_for_status()
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > 32 * 1024 * 1024:
                    raise ValueError("Source response exceeds 32 MB; configure smaller pages")
                chunks.append(chunk)
            headers = dict(response.headers)
            # iter_bytes already decoded content; retaining Content-Encoding would decode twice.
            headers.pop("content-encoding", None)
            headers.pop("content-length", None)
            return httpx.Response(
                response.status_code,
                headers=headers,
                content=b"".join(chunks),
                request=response.request,
            )
