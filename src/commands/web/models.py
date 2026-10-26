from __future__ import annotations

from typing import Any, Final
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

__all__ = ("ImageResult", "parse_image_results")

TITLE_LIMIT: Final = 256


class ImageResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    image_url: str = Field(pattern=r"^https?://")
    title: str | None = None
    page_url: str | None = None
    thumbnail_url: str | None = None

    @property
    def domain(self) -> str | None:
        source = self.page_url or self.image_url
        host = urlsplit(source).hostname
        return host.removeprefix("www.") if host else None


def parse_image_results(data: Any, limit: int) -> list[ImageResult]:
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ValueError("Unexpected SearXNG response")

    results: list[ImageResult] = []
    seen: set[str] = set()

    for item in data["results"]:
        if not isinstance(item, dict):
            continue
        image = _absolute(item.get("img_src"))
        if image is None or image in seen:
            continue
        seen.add(image)
        title = str(item.get("title") or "").strip()[:TITLE_LIMIT] or None
        results.append(
            ImageResult(
                image_url=image,
                title=title,
                page_url=_absolute(item.get("url")),
                thumbnail_url=_absolute(item.get("thumbnail_src")),
            )
        )
        if len(results) == limit:
            break

    return results


def _absolute(url: Any) -> str | None:
    """`//host/x.jpg` -> `https://host/x.jpg`, None for anything that isn't a web URL"""
    if not isinstance(url, str):
        return None
    url = url.strip()
    if url.startswith("//"):
        url = "https:" + url
    return url if url.startswith(("https://", "http://")) else None
