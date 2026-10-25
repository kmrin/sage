from __future__ import annotations

import functools
import operator
from typing import TYPE_CHECKING, Final, cast

import crescent
import hikari

from commands.guild.models import parse_color
from commands.guild.welcome import (
    MESSAGE_LIMIT,
    TITLE_LIMIT,
    welcome_embed,
    welcome_keys,
    welcome_values,
)
from core.i18n import LocaleKeys, tr
from core.model import SagePlugin, model_of
from core.permissions import guild_admin
from models.db import GuildAutoRoleConfig, GuildConfig, GuildWelcomeChannelConfig

if TYPE_CHECKING:
    from crescent.commands.options import ClassCommandOption
    from sqlalchemy.ext.asyncio import AsyncSession

plugin = SagePlugin()

NOT_SYNCED: Final = "errors.guild.not_synced"

welcome_options = welcome_keys.child("options")

set_keys = LocaleKeys("commands.guild.set")
set_group = crescent.Group(set_keys.localized("name"), set_keys.localized("description"))

auto_role_keys = set_keys.child("auto_role")
auto_role_options = auto_role_keys.child("options")
auto_role_problems = auto_role_keys.child("problems")

ROLE_MANAGERS: Final = hikari.Permissions.ADMINISTRATOR | hikari.Permissions.MANAGE_ROLES
NAME_LIMIT: Final = 100


def _text_option(
    keys: LocaleKeys, *, max_length: int
) -> ClassCommandOption[str | None, str | None]:
    option = crescent.option(
        str,
        name=keys.localized("name"),
        description=keys.localized("description"),
        default=None,
        max_length=max_length,
    )
    # crescent 1.4 types a defaulted str option as `int | DEFAULT` (upstream typo)
    return cast("ClassCommandOption[str | None, str | None]", option)


@plugin.include
@set_group.child
@guild_admin
@crescent.command(
    name=welcome_keys.localized("name"),
    description=welcome_keys.localized("description"),
)
class SetWelcomeChannel:
    channel = crescent.option(
        [hikari.GuildTextChannel, hikari.GuildNewsChannel],
        name=welcome_options.localized("channel.name"),
        description=welcome_options.localized("channel.description"),
        default=None,
    )
    title = _text_option(welcome_options.child("title"), max_length=TITLE_LIMIT)
    message = _text_option(welcome_options.child("message"), max_length=MESSAGE_LIMIT)
    color = _text_option(welcome_options.child("color"), max_length=7)
    show_avatar = crescent.option(
        bool,
        name=welcome_options.localized("show_avatar.name"),
        description=welcome_options.localized("show_avatar.description"),
        default=None,
    )
    reset = crescent.option(
        bool,
        name=welcome_options.localized("reset.name"),
        description=welcome_options.localized("reset.description"),
        default=False,
    )
    enabled = crescent.option(
        bool,
        name=welcome_options.localized("enabled.name"),
        description=welcome_options.localized("enabled.description"),
        default=True,
    )

    def apply(self, config: GuildWelcomeChannelConfig, color: hikari.Color | None) -> None:
        if self.channel is not None:
            config.channel_id = self.channel.id
            config.channel_name = (self.channel.name or str(self.channel.id))[:NAME_LIMIT]
        if self.reset:
            config.embed_title = config.embed_description = config.embed_color = None
        if self.title is not None:
            config.embed_title = self.title
        if self.message is not None:
            config.embed_description = self.message
        if color is not None:
            config.embed_color = int(color)
        if self.show_avatar is not None:
            config.show_pfp_option = self.show_avatar
        config.active = self.enabled

    async def callback(self, ctx: crescent.Context) -> None:
        guild_id, member = _guild_id(ctx), _member(ctx)
        color: hikari.Color | None = None

        if self.color is not None:
            try:
                color = parse_color(self.color)
            except ValueError:
                await ctx.respond(
                    tr(ctx, welcome_keys("invalid_color"), color=self.color), ephemeral=True
                )
                return

        problem: str | None = None

        async with model_of(ctx).database.session.begin() as session:
            config = await load_setting(session, GuildWelcomeChannelConfig, guild_id)
            if config is None:
                problem = NOT_SYNCED
            elif self.enabled and self.channel is None and config.channel_id is None:
                problem = welcome_keys("no_channel")
            else:
                self.apply(config, color)

        if problem is not None or config is None:
            await ctx.respond(tr(ctx, problem or NOT_SYNCED), ephemeral=True)
            return

        if not config.active:
            await ctx.respond(tr(ctx, welcome_keys("disabled")), ephemeral=True)
            return

        values, locale = await welcome_values(plugin.app, member)
        content = "\n".join(
            (
                tr(ctx, welcome_keys("saved"), channel=f"<#{config.channel_id}>"),
                tr(ctx, welcome_keys("hint")),
            )
        )
        await ctx.respond(
            content, embed=welcome_embed(config, member, values, locale), ephemeral=True
        )


@plugin.include
@set_group.child
@guild_admin
@crescent.command(
    name=auto_role_keys.localized("name"),
    description=auto_role_keys.localized("description"),
)
class SetAutoRole:
    role = crescent.option(
        hikari.Role,
        name=auto_role_options.localized("role.name"),
        description=auto_role_options.localized("role.description"),
        default=None,
    )
    enabled = crescent.option(
        bool,
        name=auto_role_options.localized("enabled.name"),
        description=auto_role_options.localized("enabled.description"),
        default=True,
    )

    @staticmethod
    def role_problem(role: hikari.Role, guild_id: int) -> str | None:
        if role.id == guild_id:
            return auto_role_problems("everyone")
        if role.is_managed:
            return auto_role_problems("managed")

        me = plugin.app.get_me()
        sage = plugin.app.cache.get_member(guild_id, me.id) if me else None
        if sage is None:
            return None  # not cached: the join listener in events.py logs it if Discord says no

        roles = [*sage.get_roles(), plugin.app.cache.get_role(guild_id)]
        permissions = functools.reduce(
            operator.or_, (r.permissions for r in roles if r), hikari.Permissions.NONE
        )
        if not permissions & ROLE_MANAGERS:
            return auto_role_problems("missing_permission")

        top = sage.get_top_role()
        if top is None or role.position >= top.position:
            return auto_role_problems("too_high")

        return None

    async def callback(self, ctx: crescent.Context) -> None:
        guild_id = _guild_id(ctx)
        role = self.role
        problem: str | None = None

        async with model_of(ctx).database.session.begin() as session:
            config = await load_setting(session, GuildAutoRoleConfig, guild_id)

            if config is None:
                problem = NOT_SYNCED
            elif self.enabled:
                if role is None and config.role_id is not None:
                    role = plugin.app.cache.get_role(config.role_id)
                    problem = auto_role_problems("gone") if role is None else None
                elif role is None:
                    problem = auto_role_keys("no_role")
                if problem is None and role is not None:
                    problem = self.role_problem(role, guild_id)

            if config is not None and problem is None:
                if role is not None:
                    config.role_id, config.role_name = role.id, role.name[:NAME_LIMIT]
                config.active = self.enabled

        mention = role.mention if role else ""

        if problem is not None:
            await ctx.respond(tr(ctx, problem, role=mention), ephemeral=True)
        elif not self.enabled:
            await ctx.respond(tr(ctx, auto_role_keys("disabled")), ephemeral=True)
        else:
            await ctx.respond(tr(ctx, auto_role_keys("saved"), role=mention), ephemeral=True)


async def load_setting[T: (GuildAutoRoleConfig, GuildWelcomeChannelConfig)](
    session: AsyncSession, kind: type[T], guild_id: int
) -> T | None:
    """
    The guild's row for one feature, created with defaults if missing.
    None until the sync has registered the guild (core.sync owns `guilds`).
    """
    setting = await session.get(kind, guild_id)
    if setting is None and await session.get(GuildConfig, guild_id) is not None:
        setting = kind(guild_id=guild_id)
        session.add(setting)
        await session.flush()  # fills in the column defaults
    return setting


def _guild_id(ctx: crescent.Context) -> int:
    if ctx.guild_id is None:
        raise RuntimeError("guild_admin should have stopped this command outside a server")
    return ctx.guild_id


def _member(ctx: crescent.Context) -> hikari.Member:
    if ctx.member is None:
        raise RuntimeError("guild_admin should have stopped this command outside a server")
    return ctx.member
