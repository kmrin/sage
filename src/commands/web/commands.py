from __future__ import annotations

from typing import TYPE_CHECKING, Final

import crescent
import hikari

from commands.web.searxng import search_images
from core.http import FETCH_ERRORS
from core.i18n import LocaleKeys, tr
from core.interactions import EVERYWHERE, fail_after_defer
from core.logger import get_logger
from core.model import SagePlugin, model_of
from core.paginator import PaginatedResponse

if TYPE_CHECKING:
    from commands.web.models import ImageResult

plugin = SagePlugin()
log = get_logger("Web")

search_keys = LocaleKeys("commands.web.search")
search_group = crescent.Group(search_keys.localized("name"), search_keys.localized("description"))
image_keys = search_keys.child("image")

SEARCH_COLOR: Final = hikari.Color(0x4285F4)
MAX_RESULTS: Final = 10
QUERY_LIMIT: Final = 200


@plugin.include
@search_group.child
@crescent.command(
    name=image_keys.localized("name"),
    description=image_keys.localized("description"),
    context_types=EVERYWHERE,
)
class SearchImage:
    query = crescent.option(
        str,
        name=image_keys.localized("options.query.name"),
        description=image_keys.localized("options.query.description"),
        max_length=QUERY_LIMIT,
    )

    async def callback(self, ctx: crescent.Context) -> None:
        query = self.query.strip()
        model = model_of(ctx)
        await ctx.defer()

        try:
            results = await search_images(
                model.http,
                model.settings.searxng.url,
                query,
                language=str(ctx.locale),
                limit=MAX_RESULTS,
            )
        except FETCH_ERRORS as error:
            log.warn("SearXNG image search failed: %s", error)
            await fail_after_defer(ctx, image_keys("unavailable"))
            return

        if not results:
            await fail_after_defer(ctx, image_keys("no_results"), query=query)
            return

        pages = [self.page(ctx, query, result) for result in results]
        await PaginatedResponse(pages, owner_id=ctx.user.id).send(ctx, model.miru)

    @staticmethod
    def page(ctx: crescent.Context, query: str, result: ImageResult) -> hikari.Embed:
        embed = hikari.Embed(
            title=result.title or query,
            url=result.page_url or result.image_url,
            color=SEARCH_COLOR,
        )
        embed.set_image(result.image_url)
        if result.domain:
            embed.set_footer(tr(ctx, image_keys("footer"), query=query, source=result.domain))
        return embed
