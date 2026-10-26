from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from core.http import FETCH_ERRORS, download
from core.logger import get_logger
from core.media import prepare

if TYPE_CHECKING:
    from collections.abc import Sequence

    import aiohttp

    from commands.web.models import ImageResult
    from core.media import Encoded

__all__ = ("FoundImage", "fetch_images")

log = get_logger("Web")

IMAGE_TIMEOUT: Final = 6.0  # per URL: slow hosts are skipped for the next result
TOTAL_TIMEOUT: Final = 20.0  # then answer with whatever loaded
CONCURRENCY: Final = 5


@dataclass(frozen=True, slots=True)
class FoundImage:
    result: ImageResult
    image: Encoded


async def fetch_images(
    http: aiohttp.ClientSession, results: Sequence[ImageResult], *, limit: int
) -> list[FoundImage]:
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def fetch(result: ImageResult) -> FoundImage | None:
        async with semaphore:
            for url in filter(None, (result.image_url, result.thumbnail_url)):
                try:
                    async with asyncio.timeout(IMAGE_TIMEOUT):
                        data = await download(http, url)
                    return FoundImage(result, await asyncio.to_thread(prepare, data))
                except FETCH_ERRORS as error:
                    log.debug("Skipping search image %s: %r", url, error)
        return None

    tasks = [asyncio.create_task(fetch(result)) for result in results]
    found: list[FoundImage] = []
    try:
        async with asyncio.timeout(TOTAL_TIMEOUT):
            for task in tasks:
                if (item := await task) is not None:
                    found.append(item)
                    if len(found) == limit:
                        break
    except TimeoutError:
        log.info("Image search downloads hit %ss, showing %d result(s)", TOTAL_TIMEOUT, len(found))
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    return found
