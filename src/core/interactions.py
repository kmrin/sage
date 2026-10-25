from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Final, cast

import hikari

from core.i18n import tr

if TYPE_CHECKING:
    from collections.abc import Callable

    import crescent

    from core.i18n import LocaleKeys

__all__ = ("EVERYWHERE", "fail_after_defer", "label", "send_rendered")

# Servers and Sage's DMs
EVERYWHERE: Final = [hikari.ApplicationContextType.GUILD, hikari.ApplicationContextType.BOT_DM]


def label(keys: LocaleKeys) -> str:
    """
    The localized name of a context menu command, from `keys.label`. crescent only types
    those names as str, but takes a Localized like it does for slash commands.
    """
    return cast("str", keys.localized("label"))


async def fail_after_defer(ctx: crescent.Context, key: str, /, **values: object) -> None:
    """
    A public defer can't turn into a private reply, so the "thinking..." message is
    deleted and the error goes out as a private followup instead.
    """
    await ctx.delete()
    await ctx.interaction.execute(tr(ctx, key, **values), flags=hikari.MessageFlag.EPHEMERAL)


async def send_rendered(
    ctx: crescent.Context,
    render: Callable[[], bytes],
    filename: str,
    content: hikari.UndefinedOr[str] = hikari.UNDEFINED,
) -> None:
    """
    Runs a CPU-heavy `render` off the event loop and posts the file. Defer first.
    Mentions in `content` never ping anyone.
    """
    data = await asyncio.to_thread(render)
    await ctx.respond(
        content,
        attachment=hikari.Bytes(data, filename),
        user_mentions=False,
        role_mentions=False,
        mentions_everyone=False,
    )
