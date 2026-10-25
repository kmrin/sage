from __future__ import annotations

from typing import TYPE_CHECKING, Final

from commands.web.models import parse_image_results

if TYPE_CHECKING:
    import aiohttp

    from commands.web.models import ImageResult

__all__ = ("search_images",)

SAFE_SEARCH_STRICT: Final = "2"


async def search_images(
    http: aiohttp.ClientSession, base_url: str, query: str, *, language: str, limit: int
) -> list[ImageResult]:
    params = {
        "q": query,
        "categories": "images",
        "format": "json",
        # results can land in any channel, doing this to prevent future issues...
        "safesearch": SAFE_SEARCH_STRICT,
        "language": language,
    }
    async with http.get(f"{base_url.rstrip('/')}/search", params=params) as response:
        return parse_image_results(await response.json(), limit)
