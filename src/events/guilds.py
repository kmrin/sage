"""
Keeps database updated while Sage runs.
"""

from __future__ import annotations

import crescent
import hikari

from core.logger import get_logger
from core.model import SagePlugin

plugin = SagePlugin()
log = get_logger("Guilds")


def _resync(guild_id: int, reason: str) -> None:
    plugin.model.sync.schedule_resync(plugin.app.rest, guild_id, reason=reason)


@plugin.include
@crescent.event
async def on_guild_join(event: hikari.GuildJoinEvent) -> None:
    log.info("Joined guild %s (%s)", event.guild.name, event.guild_id)
    _resync(event.guild_id, "joined guild")


@plugin.include
@crescent.event
async def on_guild_leave(event: hikari.GuildLeaveEvent) -> None:
    await plugin.model.sync.remove_guild(event.guild_id, reason="Sage was removed or left")


@plugin.include
@crescent.event
async def on_guild_update(event: hikari.GuildUpdateEvent) -> None:
    _resync(event.guild_id, "guild updated")


@plugin.include
@crescent.event
async def on_member_create(event: hikari.MemberCreateEvent) -> None:
    if not event.member.is_bot:
        _resync(event.guild_id, f"member {event.user_id} joined")


@plugin.include
@crescent.event
async def on_member_update(event: hikari.MemberUpdateEvent) -> None:
    if not event.member.is_bot:
        _resync(event.guild_id, f"member {event.user_id} updated")


@plugin.include
@crescent.event
async def on_member_delete(event: hikari.MemberDeleteEvent) -> None:
    me = plugin.app.get_me()
    if event.user.is_bot or (me is not None and event.user_id == me.id):
        return
    _resync(event.guild_id, f"member {event.user_id} left")


@plugin.include
@crescent.event
async def on_role_change(event: hikari.RoleEvent) -> None:
    _resync(event.guild_id, f"role {event.role_id} changed")
