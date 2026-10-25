from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

import hikari
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ("WELCOME_COLOR", "WelcomeValues", "parse_color")

WELCOME_COLOR: Final = hikari.Color(0x9B59B6)

_HEX_COLOR: Final = re.compile(r"^#?(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def parse_color(text: str) -> hikari.Color:
    text = text.strip()
    if not _HEX_COLOR.fullmatch(text):
        raise ValueError(f"{text!r} is not a hex color")
    return hikari.Color.from_hex_code(text)


class WelcomeValues(BaseModel):
    """What a welcome title or message can refer to, e.g. `Welcome {user} to {server}!`"""

    model_config = ConfigDict(frozen=True)

    user: str
    username: str
    server: str
    member_count: str

    @classmethod
    def for_member(
        cls, member: hikari.Member, server: str, member_count: int | None
    ) -> WelcomeValues:
        return cls(
            user=member.mention,
            username=member.display_name,
            server=server,
            member_count=str(member_count) if member_count else "?",
        )

    def as_mapping(self) -> Mapping[str, str]:
        return self.model_dump()

    def render(self, template: str) -> str:
        values = self.as_mapping()
        pattern = re.compile(r"\{(" + "|".join(map(re.escape, values)) + r")\}")
        return pattern.sub(lambda match: values[match[1]], template.replace("\\n", "\n"))
