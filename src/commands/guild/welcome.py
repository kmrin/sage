"""
Welcome embed building, shared by /set welcome_channel's preview and the member-join listener.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import hikari

from commands.guild.models import WELCOME_COLOR, WelcomeValues
from core.i18n import LocaleKeys, t

if TYPE_CHECKING:
    from models.db import GuildWelcomeChannelConfig

__all__ = ("MESSAGE_LIMIT", "TITLE_LIMIT", "welcome_embed", "welcome_keys", "welcome_values")

welcome_keys = LocaleKeys("commands.guild.set.welcome_channel")

TITLE_LIMIT: Final = 256
MESSAGE_LIMIT: Final = 4096


async def welcome_values(
    app: hikari.GatewayBot, member: hikari.Member
) -> tuple[WelcomeValues, hikari.Locale | str]:
    # hikari doesn't bump member_count on joins, but the (chunked) member cache is current
    cached_members = len(app.cache.get_members_view_for_guild(member.guild_id))

    if (guild := app.cache.get_guild(member.guild_id)) is not None:
        name, count, locale = guild.name, guild.member_count, guild.preferred_locale
    else:
        rest = await app.rest.fetch_guild(member.guild_id)
        name, count, locale = rest.name, rest.approximate_member_count, rest.preferred_locale

    return WelcomeValues.for_member(member, name, cached_members or count), locale


def welcome_embed(
    config: GuildWelcomeChannelConfig,
    member: hikari.Member,
    values: WelcomeValues,
    locale: hikari.Locale | str | None,
) -> hikari.Embed:
    def text(custom: str | None, default: str, limit: int) -> str:
        rendered = (
            values.render(custom)
            if custom
            else t(welcome_keys(default), locale, **values.as_mapping())
        )
        return rendered[:limit]

    embed = hikari.Embed(
        title=text(config.embed_title, "default_title", TITLE_LIMIT),
        description=text(config.embed_description, "default_message", MESSAGE_LIMIT),
        color=WELCOME_COLOR if config.embed_color is None else hikari.Color(config.embed_color),
    )

    if config.show_pfp_option:
        embed.set_thumbnail(member.display_avatar_url)

    return embed
