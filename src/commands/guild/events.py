from __future__ import annotations

import crescent
import hikari

from commands.guild.welcome import welcome_embed, welcome_values
from core.i18n import LocaleKeys, t
from core.logger import get_logger
from core.model import SagePlugin
from models.db import GuildAutoRoleConfig, GuildWelcomeChannelConfig

plugin = SagePlugin()
log = get_logger("Guild")

auto_role_keys = LocaleKeys("commands.guild.set.auto_role")


@plugin.include
@crescent.event
async def on_member_join(event: hikari.MemberCreateEvent) -> None:
    if event.member.is_bot:
        return

    async with plugin.model.database.session() as session:
        auto_role = await session.get(GuildAutoRoleConfig, event.guild_id)
        welcome = await session.get(GuildWelcomeChannelConfig, event.guild_id)

    if auto_role is not None and auto_role.active and auto_role.role_id is not None:
        await give_auto_role(event.member, auto_role.role_id)

    if welcome is not None and welcome.active and welcome.channel_id is not None:
        await send_welcome(event.member, welcome, welcome.channel_id)


async def give_auto_role(member: hikari.Member, role_id: int) -> None:
    guild = plugin.app.cache.get_guild(member.guild_id)
    reason = t(auto_role_keys("audit_reason"), guild.preferred_locale if guild else None)

    try:
        await member.add_role(role_id, reason=reason)
    except hikari.HTTPError as error:
        log.warn(
            "Couldn't give auto role %s to %s (%s) in guild %s: %s",
            role_id,
            member.username,
            member.id,
            member.guild_id,
            error,
        )
        return

    log.info(
        "Gave auto role %s to %s (%s) in %s", role_id, member.username, member.id, member.guild_id
    )


async def send_welcome(
    member: hikari.Member, config: GuildWelcomeChannelConfig, channel_id: int
) -> None:
    try:
        values, locale = await welcome_values(plugin.app, member)
        await plugin.app.rest.create_message(
            channel_id, embed=welcome_embed(config, member, values, locale)
        )
    except hikari.HTTPError as error:
        log.warn(
            "Couldn't welcome %s (%s) in channel %s of guild %s: %s",
            member.username,
            member.id,
            channel_id,
            member.guild_id,
            error,
        )
