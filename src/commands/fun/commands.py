from __future__ import annotations

import asyncio
import functools
from typing import TYPE_CHECKING, Final

import crescent
import hikari

from commands.fun.apis import fetch_cat, fetch_dog
from commands.fun.edits import deepfry, jpegify, pixelate
from commands.fun.images import render_quote, render_sonic
from commands.fun.models import CatRequest, DiceRoll, MentionKind, clean_text
from core.http import FETCH_ERRORS, TooLargeError, download
from core.i18n import LocaleKeys, tr
from core.interactions import EVERYWHERE, fail_after_defer, label, send_rendered
from core.logger import get_logger
from core.media import BadImageError, Encoded, fit_upload, load, prepare
from core.model import SagePlugin, model_of
from core.options import optional_text

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from core.media import Animation

plugin = SagePlugin()
log = get_logger("Fun")

fun_keys = LocaleKeys("commands.fun")
dog_keys = fun_keys.child("dog")
cat_keys = fun_keys.child("cat")
cat_options = cat_keys.child("options")
roll_keys = fun_keys.child("roll")
sonic_keys = fun_keys.child("sonic")
sonic_message_keys = fun_keys.child("sonic_message")
quote_keys = fun_keys.child("quote_message")
deepfry_keys = fun_keys.child("deepfry_message")
jpeg_keys = fun_keys.child("jpeg_message")
pixelate_keys = fun_keys.child("pixelate_message")
edit_keys = fun_keys.child("image_edit")

DOG_COLOR: Final = hikari.Color(0xC68642)
CAT_COLOR: Final = hikari.Color(0xF4A261)
SONIC_LIMIT: Final = 300
CAT_SAYS_LIMIT: Final = 100
MESSAGE_TEXT_LIMIT: Final = 1000
AVATAR_SIZE: Final = 1024
_STATIC_STICKERS: Final = frozenset(
    {hikari.StickerFormatType.PNG, hikari.StickerFormatType.APNG, hikari.StickerFormatType.GIF}
)


@plugin.include
@crescent.command(
    name=dog_keys.localized("name"),
    description=dog_keys.localized("description"),
    context_types=EVERYWHERE,
)
class Dog:
    async def callback(self, ctx: crescent.Context) -> None:
        await ctx.defer()

        http = model_of(ctx).http
        try:
            photo = await fetch_dog(http)
            image = await asyncio.to_thread(prepare, await download(http, photo.url))
        except FETCH_ERRORS as error:
            log.warn("dog.ceo request failed: %s", error)
            await fail_after_defer(ctx, dog_keys("error"))
            return

        embed = hikari.Embed(title=tr(ctx, dog_keys("title")), color=DOG_COLOR)
        embed.set_image(hikari.Bytes(image.data, f"dog.{image.extension}"))
        if photo.breed:
            embed.set_footer(tr(ctx, dog_keys("breed"), breed=photo.breed))
        await ctx.respond(embed=embed)


@plugin.include
@crescent.command(
    name=cat_keys.localized("name"),
    description=cat_keys.localized("description"),
    context_types=EVERYWHERE,
)
class Cat:
    gif = crescent.option(
        bool,
        name=cat_options.localized("gif.name"),
        description=cat_options.localized("gif.description"),
        default=False,
    )
    says = optional_text(cat_options.child("says"), max_length=CAT_SAYS_LIMIT)

    async def callback(self, ctx: crescent.Context) -> None:
        says = clean_text(self.says, mention_resolver()) if self.says else None
        await ctx.defer()

        try:
            cat = await fetch_cat(model_of(ctx).http, CatRequest(gif=self.gif, says=says or None))
            image = await asyncio.to_thread(prepare, cat.data)
        except FETCH_ERRORS as error:
            log.warn("cataas request failed: %s", error)
            await fail_after_defer(ctx, cat_keys("error"))
            return

        embed = hikari.Embed(title=tr(ctx, cat_keys("title")), color=CAT_COLOR)
        embed.set_image(hikari.Bytes(image.data, f"cat.{image.extension}"))
        await ctx.respond(embed=embed)


@plugin.include
@crescent.command(
    name=roll_keys.localized("name"),
    description=roll_keys.localized("description"),
    context_types=EVERYWHERE,
)
class Roll:
    sides = crescent.option(
        int,
        name=roll_keys.localized("options.sides.name"),
        description=roll_keys.localized("options.sides.description"),
        default=6,
        min_value=2,
        max_value=1000,
    )

    async def callback(self, ctx: crescent.Context) -> None:
        result = DiceRoll.roll(self.sides)
        await ctx.respond(tr(ctx, roll_keys("response"), value=result.value, sides=result.sides))


@plugin.include
@crescent.command(
    name=sonic_keys.localized("name"),
    description=sonic_keys.localized("description"),
    context_types=EVERYWHERE,
)
class Sonic:
    text = crescent.option(
        str,
        name=sonic_keys.localized("options.text.name"),
        description=sonic_keys.localized("options.text.description"),
        max_length=SONIC_LIMIT,
    )

    async def callback(self, ctx: crescent.Context) -> None:
        text = clean_text(self.text, mention_resolver())
        if not text:
            await ctx.respond(tr(ctx, fun_keys("no_text")), ephemeral=True)
            return
        await ctx.defer()
        await send_rendered(ctx, functools.partial(render_sonic, text), "sonic.png")


@plugin.include
@crescent.message_command(name=label(sonic_message_keys), context_types=EVERYWHERE)
async def sonic_message(ctx: crescent.Context, message: hikari.Message) -> None:
    text = message_text(message)
    if not text:
        await ctx.respond(tr(ctx, fun_keys("no_text")), ephemeral=True)
        return
    await ctx.defer()
    await send_rendered(ctx, functools.partial(render_sonic, text), "sonic.png")


@plugin.include
@crescent.message_command(name=label(quote_keys), context_types=EVERYWHERE)
async def quote_message(ctx: crescent.Context, message: hikari.Message) -> None:
    text = message_text(message)
    if not text:
        await ctx.respond(tr(ctx, fun_keys("no_text")), ephemeral=True)
        return

    await ctx.defer()

    author = message.author
    avatar_url = author.make_avatar_url(file_format="PNG", size=AVATAR_SIZE)
    try:
        avatar = await download(model_of(ctx).http, str(avatar_url or author.default_avatar_url))
    except FETCH_ERRORS as error:
        log.warn("Couldn't download %s's avatar for a quote: %s", author.username, error)
        avatar = None  # the card still works, just without the picture

    name = message.member.display_name if message.member else _name(author)
    render = functools.partial(render_quote, avatar, text, name, author.username)
    await send_rendered(ctx, render, "quote.png")


@plugin.include
@crescent.message_command(name=label(deepfry_keys), context_types=EVERYWHERE)
async def deepfry_message(ctx: crescent.Context, message: hikari.Message) -> None:
    await edit_message_image(ctx, message, deepfry, "deepfried")


@plugin.include
@crescent.message_command(name=label(jpeg_keys), context_types=EVERYWHERE)
async def jpeg_message(ctx: crescent.Context, message: hikari.Message) -> None:
    await edit_message_image(ctx, message, jpegify, "jpeg")


@plugin.include
@crescent.message_command(name=label(pixelate_keys), context_types=EVERYWHERE)
async def pixelate_message(ctx: crescent.Context, message: hikari.Message) -> None:
    await edit_message_image(ctx, message, pixelate, "pixelated")


async def edit_message_image(
    ctx: crescent.Context,
    message: hikari.Message,
    edit: Callable[[Animation], Encoded],
    name: str,
) -> None:
    """Downloads the message's first image, applies `edit` and posts the result."""
    url = message_image_url(message)
    if url is None:
        await ctx.respond(tr(ctx, edit_keys("no_image")), ephemeral=True)
        return

    await ctx.defer()

    try:
        data = await download(model_of(ctx).http, url)
        encoded = await asyncio.to_thread(lambda: fit_upload(load(data), edit))
    except TooLargeError:
        await fail_after_defer(ctx, edit_keys("too_big"))
        return
    except BadImageError:
        await fail_after_defer(ctx, edit_keys("not_an_image"))
        return
    except FETCH_ERRORS as error:
        log.warn("Couldn't download %s for an image edit: %s", url, error)
        await fail_after_defer(ctx, edit_keys("download_failed"))
        return

    await ctx.respond(attachment=hikari.Bytes(encoded.data, f"{name}.{encoded.extension}"))


def message_image_url(message: hikari.Message) -> str | None:
    """The first image in an attachment, embed or sticker (in that order)."""
    for attachment in message.attachments:
        if (attachment.media_type or "").startswith("image/"):
            return attachment.url
    for embed in message.embeds:
        for media in (embed.image, embed.thumbnail):
            if media is not None and (media.proxy_url or media.url):
                return media.proxy_url or media.url
    for sticker in message.stickers:
        if sticker.format_type in _STATIC_STICKERS:
            return str(sticker.make_url())
    return None


def message_text(message: hikari.Message) -> str:
    content = (message.content or "")[:MESSAGE_TEXT_LIMIT]
    users = message.user_mentions if message.user_mentions is not hikari.UNDEFINED else None
    return clean_text(content, mention_resolver(users))


def mention_resolver(
    users: Mapping[hikari.Snowflake, hikari.User] | None = None,
) -> Callable[[MentionKind, int], str | None]:
    """Names for `<@id>`, `<@&id>` and `<#id>`, from the message's mentions or the cache."""
    cache = plugin.app.cache

    def resolve(kind: MentionKind, snowflake: int) -> str | None:
        if kind == "user":
            user = (users or {}).get(hikari.Snowflake(snowflake)) or cache.get_user(snowflake)
            return _name(user) if user else None
        if kind == "role":
            role = cache.get_role(snowflake)
            return role.name if role else None
        channel = cache.get_guild_channel(snowflake)
        return channel.name if channel else None

    return resolve


def _name(user: hikari.User) -> str:
    return user.global_name or user.username
