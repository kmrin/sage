from __future__ import annotations

from typing import Final

import aiohttp

__all__ = (
    "FETCH_ERRORS",
    "MAX_UPLOAD",
    "TIMEOUT",
    "TooLargeError",
    "create_session",
    "download",
    "read_capped",
)

TIMEOUT: Final = aiohttp.ClientTimeout(total=15, connect=5)
MAX_UPLOAD: Final = 10 * 1024 * 1024  # Discord's attachment limit in servers without boosts
_CHUNK: Final = 64 * 1024


class TooLargeError(ValueError):
    """The file is bigger than Sage is willing to download or Discord lets it upload"""


# What a failed fetch looks like: network trouble, a bad status, or a response we can't use
FETCH_ERRORS: Final[tuple[type[Exception], ...]] = (aiohttp.ClientError, TimeoutError, ValueError)


def create_session(version: str) -> aiohttp.ClientSession:
    """The shared session for calling outside APIs. Create it inside the running event loop."""
    return aiohttp.ClientSession(
        timeout=TIMEOUT,
        headers={"User-Agent": f"Sage/{version} (+https://github.com/kmrin/sage)"},
        raise_for_status=True,
    )


async def read_capped(
    http: aiohttp.ClientSession,
    url: str,
    *,
    limit: int = MAX_UPLOAD,
) -> tuple[bytes, str]:
    async with http.get(url) as response:
        if response.content_length is not None and response.content_length > limit:
            raise TooLargeError(f"{url} is {response.content_length} bytes")

        data = bytearray()
        async for chunk in response.content.iter_chunked(_CHUNK):
            data += chunk
            if len(data) > limit:
                raise TooLargeError(f"{url} is over {limit} bytes")

        return bytes(data), response.content_type


async def download(
    http: aiohttp.ClientSession,
    url: str,
    *,
    limit: int = MAX_UPLOAD,
) -> bytes:
    data, _ = await read_capped(http, url, limit=limit)
    return data
