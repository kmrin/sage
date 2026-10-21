"""
Last-resort handlers: log unexpected errors and tell the user about it.
"""

from __future__ import annotations

import crescent
import hikari

from core.i18n import tr
from core.logger import get_logger
from core.model import SagePlugin

plugin = SagePlugin()
log = get_logger("Commands")


@plugin.include
@crescent.catch_command(Exception)
async def on_command_error(error: Exception, ctx: crescent.Context) -> None:
    log.error(
        "/%s failed for %s (%s) in %s",
        ctx.command,
        ctx.user.username,
        ctx.user.id,
        ctx.guild_id or "DMs",
        exc_info=error,
    )

    try:
        await ctx.respond(tr(ctx, "errors.unexpected"), ephemeral=True)
    except hikari.HTTPError as http_error:
        log.warn("Couldn't tell the user about the /%s failure: %s", ctx.command, http_error)


@plugin.include
@crescent.catch_event(Exception)
async def on_event_error(error: Exception, event: hikari.Event) -> None:
    log.error("Listener for %s for failed", type(event).__name__, exc_info=error)
