"""
Outside APIs used by the fun commands.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import aiohttp

from commands.fun.models import CatImage, DogPhoto
from core.http import TooLargeError, read_capped

if TYPE_CHECKING:
    from commands.fun.models import CatRequest

__all__ = ("fetch_cat", "fetch_dog")

DOG_API: Final = "https://dog.ceo/api/breeds/image/random"
CAT_ATTEMPTS: Final = 3


async def fetch_dog(http: aiohttp.ClientSession) -> DogPhoto:
    async with http.get(DOG_API) as response:
        return DogPhoto.from_api(await response.json())


async def fetch_cat(http: aiohttp.ClientSession, request: CatRequest) -> CatImage:
    error: Exception | None = None
    for _ in range(CAT_ATTEMPTS):
        try:
            data, content_type = await read_capped(http, request.url)
        except TooLargeError as too_large:
            error = too_large
        except aiohttp.ClientResponseError as response_error:
            if response_error.status < 500:
                raise
            error = response_error
        else:
            return CatImage(data=data, content_type=content_type)
    assert error is not None
    raise error
