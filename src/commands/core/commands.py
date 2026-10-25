from __future__ import annotations

import platform
from typing import Final

import crescent
import hikari

from commands.core.models import Latency
from core.i18n import LocaleKeys, tr
from core.model import SagePlugin, model_of

plugin = SagePlugin()

ping_keys = LocaleKeys("commands.core.ping")

about_keys = LocaleKeys("commands.core.about")
about_fields = about_keys.child("fields")
about_values = about_keys.child("values")

ABOUT_COLOR: Final = hikari.Color(0x9B59B6)
ABOUT_DEV: Final = "km_rin"
ABOUT_FALLBACK_NAME: Final = "Sage"
ABOUT_REPO: Final = "https://github.com/kmrin/sage"
ABOUT_TOS_URL: Final = f"{ABOUT_REPO}/blob/main/src/assets/docs/terms-of-service.md"
ABOUT_PP_URL: Final = f"{ABOUT_REPO}/blob/main/src/assets/docs/privacy-policy.md"


@plugin.include
@crescent.command(
    name=ping_keys.localized("name"),
    description=ping_keys.localized("description"),
)
class Ping:
    async def callback(self, ctx: crescent.Context) -> None:
        latency = Latency(seconds=plugin.app.heartbeat_latency)
        if latency.milliseconds is None:
            await ctx.respond(tr(ctx, ping_keys("response_pending")), ephemeral=True)
            return
        await ctx.respond(tr(ctx, ping_keys("response"), latency=latency.milliseconds))


@plugin.include
@crescent.command(
    name=about_keys.localized("name"),
    description=about_keys.localized("description"),
)
class About:
    @staticmethod
    def gen_about_embed(ctx: crescent.Context) -> hikari.Embed:
        model = model_of(ctx)
        me = plugin.app.get_me()
        latency = Latency(seconds=plugin.app.heartbeat_latency)

        latency_text = (
            tr(ctx, about_values("latency"), latency=latency.milliseconds)
            if latency.milliseconds is not None
            else tr(ctx, about_values("latency_pending"))
        )
        stack = " | ".join(
            (
                f"Python `{platform.python_version()}`",
                f"hikari `{hikari.__version__}`",
                f"crescent `{crescent.__version__}`",
            )
        )

        embed = hikari.Embed(
            title=tr(ctx, about_keys("title"), name=me.username if me else ABOUT_FALLBACK_NAME),
            description=tr(ctx, about_keys("summary")),
            color=ABOUT_COLOR,
            url=ABOUT_REPO,
        )

        if me is not None:
            embed.set_thumbnail(me.display_avatar_url)

        inline_fields = (
            ("version", f"`v{model.settings.version}`"),
            ("developer", f"`{ABOUT_DEV}`"),
            ("host", f"<@{model.settings.discord.owner_id}>"),
            ("servers", f"`{len(plugin.app.cache.get_guilds_view())}`"),
            ("latency", latency_text),
            ("uptime", f"<t:{int(model.started_at.timestamp())}:R>"),
        )
        for key, value in inline_fields:
            embed.add_field(tr(ctx, about_fields(key)), value, inline=True)

        links = tr(
            ctx, about_values("links"),
            source=ABOUT_REPO, terms=ABOUT_TOS_URL, privacy=ABOUT_PP_URL
        )
        
        embed.add_field(tr(ctx, about_fields("stack")), stack)
        embed.add_field(tr(ctx, about_fields("links")), links)
        embed.set_footer(tr(ctx, about_keys("footer")))

        return embed

    async def callback(self, ctx: crescent.Context) -> None:
        await ctx.respond(embed=self.gen_about_embed(ctx))
