from __future__ import annotations

from typing import TYPE_CHECKING, cast

import crescent

if TYPE_CHECKING:
    from crescent.commands.options import ClassCommandOption

    from core.i18n import LocaleKeys

__all__ = ("optional_text",)


def optional_text(
    keys: LocaleKeys, *, max_length: int | None = None
) -> ClassCommandOption[str | None, str | None]:
    """
    An optional text option named and described by `keys.name` and `keys.description`.
    Use it instead of `crescent.option(str, default=None)`, which crescent 1.4 types as
    `int | None` (upstream typo).
    """
    option = crescent.option(
        str,
        name=keys.localized("name"),
        description=keys.localized("description"),
        default=None,
        max_length=max_length,
    )
    return cast("ClassCommandOption[str | None, str | None]", option)
