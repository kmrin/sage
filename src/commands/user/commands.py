from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Final

import crescent
import hikari

from commands.user.images import render_petpet
from core.http import FETCH_ERRORS, download
from core.i18n import LocaleKeys, tr
from core.interactions import EVERYWHERE, fail_after_defer, send_rendered
from core.logger import get_logger
from core.model import SagePlugin, model_of

if TYPE_CHECKING:
    from crescent.commands.options import ClassCommandOption

plugin = SagePlugin()
log = get_logger("User")

user_keys = LocaleKeys("commands.user")
avatar_keys = user_keys.child("avatar")
banner_keys = user_keys.child("banner")
pet_keys = user_keys.child("pet")
member_option = user_keys.child("member_option")

USER_COLOR: Final = hikari.Color(0x9B59B6)
PET_AVATAR_SIZE: Final = 256


def _member_option() -> ClassCommandOption[hikari.User | None, hikari.User | None]:
    return crescent.option(
        hikari.User,
        name=member_option.localized("name"),
        description=member_option.localized("description"),
        default=None,
    )


@plugin.include
@crescent.command(
    name=avatar_keys.localized("name"),
    description=avatar_keys.localized("description"),
    context_types=EVERYWHERE,
)
class Avatar:
    member = _member_option()

    async def callback(self, ctx: crescent.Context) -> None:
        target = _target(ctx, self.member)
        url = str(target.display_avatar_url)  # the server avatar when they have one

        embed = hikari.Embed(
            title=tr(ctx, avatar_keys("title"), name=_name(target)),
            description=tr(ctx, user_keys("open_original"), url=url),
            color=USER_COLOR,
        )
        embed.set_image(url)
        await ctx.respond(embed=embed, ephemeral=True)


@plugin.include
@crescent.command(
    name=banner_keys.localized("name"),
    description=banner_keys.localized("description"),
    context_types=EVERYWHERE,
)
class Banner:
    member = _member_option()

    async def callback(self, ctx: crescent.Context) -> None:
        target = _target(ctx, self.member)
        await ctx.defer(ephemeral=True)

        try:
            user = await plugin.app.rest.fetch_user(target.id)
        except hikari.HTTPError as error:
            log.warn("Couldn't fetch user %s for /banner: %s", target.id, error)
            await ctx.respond(tr(ctx, banner_keys("error")), ephemeral=True)
            return

        name = _name(target)
        banner = user.make_banner_url(size=4096)

        if banner is not None:
            url = str(banner)
            embed = hikari.Embed(
                title=tr(ctx, banner_keys("title"), name=name),
                description=tr(ctx, user_keys("open_original"), url=url),
                color=user.accent_color or USER_COLOR,
            )
            embed.set_image(url)
        elif user.accent_color is not None:
            embed = hikari.Embed(
                description=tr(
                    ctx, banner_keys("accent_only"), name=name, color=user.accent_color.hex_code
                ),
                color=user.accent_color,
            )
        else:
            await ctx.respond(tr(ctx, banner_keys("none"), name=name), ephemeral=True)
            return

        await ctx.respond(embed=embed, ephemeral=True)


@plugin.include
@crescent.command(
    name=pet_keys.localized("name"),
    description=pet_keys.localized("description"),
    context_types=EVERYWHERE,
)
class Pet:
    member = _member_option()

    async def callback(self, ctx: crescent.Context) -> None:
        target = _target(ctx, self.member)
        await ctx.defer()

        try:
            avatar = await download(model_of(ctx).http, _still_avatar_url(target))
        except FETCH_ERRORS as error:
            log.warn("Couldn't download %s's avatar for /pet: %s", target.id, error)
            await fail_after_defer(ctx, pet_keys("error"))
            return

        author = ctx.member or ctx.user
        content = tr(ctx, pet_keys("response"), author=_name(author), target=_name(target))
        await send_rendered(ctx, functools.partial(render_petpet, avatar), "petpet.gif", content)


def _target(ctx: crescent.Context, member: hikari.User | None) -> hikari.User:
    """The chosen member, or whoever ran the command (as a server member when possible)."""
    return member or ctx.member or ctx.user


def _name(user: hikari.User) -> str:
    if isinstance(user, hikari.Member):
        return user.display_name
    return user.global_name or user.username


def _still_avatar_url(user: hikari.User) -> str:
    url = None
    if isinstance(user, hikari.Member):
        url = user.make_guild_avatar_url(file_format="PNG", size=PET_AVATAR_SIZE)
    url = url or user.make_avatar_url(file_format="PNG", size=PET_AVATAR_SIZE)
    return str(url or user.default_avatar_url)
