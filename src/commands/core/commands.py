from __future__ import annotations

import crescent

from commands.core.models import Latency
from core.i18n import LocaleKeys, tr
from core.model import SagePlugin

plugin = SagePlugin()
ping_keys = LocaleKeys("commands.core.ping")


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
