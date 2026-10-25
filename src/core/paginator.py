from __future__ import annotations

from typing import TYPE_CHECKING, Final

import hikari
from miru.ext import nav

from core.i18n import t

if TYPE_CHECKING:
    from collections.abc import Sequence

    import crescent
    import miru

__all__ = ("PaginatedResponse",)

DEFAULT_TIMEOUT: Final = 300.0
NOT_YOURS: Final = "errors.paginator.not_yours"

type Page = str | hikari.Embed | Sequence[hikari.Embed]


class PaginatedResponse(nav.NavigatorView):
    def __init__(
        self, pages: Sequence[Page], *, owner_id: int, timeout: float = DEFAULT_TIMEOUT
    ) -> None:
        if not pages:
            raise ValueError("PaginatedResponse needs at least one page")
        super().__init__(
            pages=pages,
            items=[
                nav.FirstButton(emoji="⏮️"),
                nav.PrevButton(emoji="◀️"),
                nav.IndicatorButton(),
                nav.NextButton(emoji="▶️"),
                nav.LastButton(emoji="⏭️"),
            ],
            timeout=timeout,
        )
        self.owner_id = owner_id
        self._sage_pages = list(pages)

    async def view_check(self, context: miru.ViewContext, /) -> bool:
        if context.user.id == self.owner_id:
            return True
        await context.respond(t(NOT_YOURS, context.locale), flags=hikari.MessageFlag.EPHEMERAL)
        return False

    async def send(
        self, ctx: crescent.Context, client: miru.Client, *, ephemeral: bool = False
    ) -> None:
        if len(self._sage_pages) == 1:
            await _respond(ctx, self._sage_pages[0], ephemeral=ephemeral)
            return

        builder = await self.build_response_async(client, ephemeral=ephemeral)
        message = await _respond(
            ctx,
            self._sage_pages[0],
            ephemeral=ephemeral,
            components=builder.components or hikari.UNDEFINED,
        )
        client.start_view(self, bind_to=message)


async def _respond(
    ctx: crescent.Context,
    page: Page,
    *,
    ephemeral: bool,
    components: hikari.UndefinedOr[Sequence[hikari.api.ComponentBuilder]] = hikari.UNDEFINED,
) -> hikari.Message:
    if isinstance(page, str):
        content, embeds = page, hikari.UNDEFINED
    else:
        content, embeds = hikari.UNDEFINED, [page] if isinstance(page, hikari.Embed) else list(page)
    message = await ctx.respond(
        content, embeds=embeds, components=components, ephemeral=ephemeral, ensure_message=True
    )
    if message is None:
        raise RuntimeError("crescent didn't return the message it was asked to ensure")
    return message
