from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from core.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Iterator
    
    import hikari

__all__ = ("Emojis", "MissingEmojisError")

log = get_logger("Emojis")


class MissingEmojisError(RuntimeError):
    """Emojis the code relies on haven't been uploaded to this application"""


class Emojis:
    REQUIRED: ClassVar[frozenset[str]] = frozenset({
        
    })
    
    __slots__ = ("_by_name",)
    
    def __init__(self) -> None:
        self._by_name: dict[str, hikari.KnownCustomEmoji] = {}
    
    async def load(self, rest: hikari.api.RESTClient, application_id: int) -> None:
        fetched = await rest.fetch_application_emojis(application_id)
        self._by_name = {emoji.name: emoji for emoji in fetched}
        
        if missing := self.REQUIRED - self._by_name.keys():
            raise MissingEmojisError(f"Missing emojis found: {', '.join(sorted(missing))}")
        
        log.info(
            "Loaded %d app emoji(s)%s",
            len(self._by_name),
            f": {', '.join(sorted(self._by_name))}" if self._by_name else "",
        )
    
    def __getitem__(self, key: str) -> hikari.KnownCustomEmoji:
        try:
            return self._by_name[key]
        except KeyError:
            raise KeyError(
                f"No app emoji named {key!r}; is it uploaded and in Emojis.REQUIRED?"
            ) from None

    def __contains__(self, item) -> bool:
        return item in self._by_name
    
    def __iter__(self) -> Iterator[str]:
        return iter(self._by_name)

    def __len__(self) -> int:
        return len(self._by_name)
