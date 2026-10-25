from __future__ import annotations

import random
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final, Literal
from urllib.parse import quote, urlsplit

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ("CatImage", "CatRequest", "DiceRoll", "DogPhoto", "MentionKind", "clean_text")

type MentionKind = Literal["user", "role", "channel"]

CAT_API: Final = "https://cataas.com"
_CAT_EXTENSIONS: Final = {"image/gif": "gif", "image/png": "png", "image/webp": "webp"}


class DiceRoll(BaseModel):
    model_config = ConfigDict(frozen=True)

    sides: int = Field(ge=2)
    value: int = Field(ge=1)

    @classmethod
    def roll(cls, sides: int) -> DiceRoll:
        return cls(sides=sides, value=random.randint(1, sides))


class DogPhoto(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str = Field(pattern=r"^https://")
    breed: str | None = None

    @classmethod
    def from_api(cls, data: Any) -> DogPhoto:
        """`{"message": "https://images.dog.ceo/breeds/setter-irish/x.jpg", "status": "success"}`"""
        if not isinstance(data, dict) or data.get("status") != "success":
            raise ValueError(f"Unexpected dog.ceo response: {data!r}")
        url = str(data.get("message", ""))
        return cls(url=url, breed=_breed(url))


def _breed(url: str) -> str | None:
    # dog.ceo names folders "<breed>-<sub-breed>": "setter-irish" is an Irish Setter
    parts = urlsplit(url).path.strip("/").split("/")
    if len(parts) < 2 or parts[0] != "breeds":
        return None
    return " ".join(reversed(parts[1].split("-"))).title()


class CatRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    gif: bool = False
    says: str | None = None

    @property
    def url(self) -> str:
        path = "/cat/gif" if self.gif else "/cat"
        if self.says:
            path += "/says/" + quote(self.says, safe="")
        return CAT_API + path


class CatImage(BaseModel):
    model_config = ConfigDict(frozen=True)

    data: bytes
    content_type: str

    @property
    def filename(self) -> str:
        return f"cat.{_CAT_EXTENSIONS.get(self.content_type, 'jpg')}"


_MENTION: Final = re.compile(r"<(@!?|@&|#)(\d+)>")
_CUSTOM_EMOJI: Final = re.compile(r"<a?:(\w+):\d+>")
_TIMESTAMP: Final = re.compile(r"<t:(-?\d+)(?::[tTdDfFR])?>")
_MARKDOWN: Final = re.compile(r"\*\*|__|~~|\|\||`+")
# Emoji the font can't draw (it would show empty boxes)
_EMOJI: Final = re.compile(
    "[\U0001f000-\U0001faff\U00002600-\U000027bf\U00002b00-\U00002bff\U0000fe0f\U0000200d]"
)
_SPACES: Final = re.compile(r"[ \t]+")
_MENTION_KINDS: Final[dict[str, tuple[MentionKind, str]]] = {
    "@": ("user", "@"),
    "@!": ("user", "@"),
    "@&": ("role", "@"),
    "#": ("channel", "#"),
}


def clean_text(text: str, resolve: Callable[[MentionKind, int], str | None]) -> str:
    """
    Turns Discord markup into plain text for the images:
    `<@123>` -> `@name` (via `resolve`), `<:blob:1>` -> `:blob:`, timestamps -> dates,
    and drops markdown symbols and emoji the font can't draw.
    """

    def mention(match: re.Match[str]) -> str:
        kind, prefix = _MENTION_KINDS[match[1]]
        return prefix + (resolve(kind, int(match[2])) or kind)

    def timestamp(match: re.Match[str]) -> str:
        try:
            return datetime.fromtimestamp(int(match[1]), UTC).strftime("%Y-%m-%d %H:%M UTC")
        except OverflowError, OSError, ValueError:
            return match[0]

    text = _MENTION.sub(mention, text)
    text = _CUSTOM_EMOJI.sub(r":\1:", text)
    text = _TIMESTAMP.sub(timestamp, text)
    text = _MARKDOWN.sub("", text)
    text = _EMOJI.sub("", text)
    lines = (_SPACES.sub(" ", line).strip() for line in text.splitlines())
    return "\n".join(lines).strip()
