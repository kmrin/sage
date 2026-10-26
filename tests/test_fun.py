from __future__ import annotations

import io
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import aiohttp
import crescent
import hikari
import pytest
from crescent.locale import str_or_build_locale
from PIL import Image

from conftest import make_ctx
from commands.fun import apis
from core import http
from commands.fun.images import QUOTE_SIZE, fit_text, render_quote, render_sonic, wrap, _font
from commands.fun.models import CatImage, CatRequest, DiceRoll, DogPhoto, clean_text
from core.i18n import t

EVERYWHERE = {hikari.ApplicationContextType.GUILD, hikari.ApplicationContextType.BOT_DM}


def _commands() -> Any:
    from commands.fun import commands

    return commands


@pytest.fixture
def client() -> crescent.Client:
    bot = hikari.GatewayBot("MTAwMDAwMDAwMDAwMDAwMDAx.fake.token", banner=None, logs=None, suppress_optimization_warning=True)
    client = crescent.Client(bot, model=None)
    client.plugins.load("commands.fun.commands")
    return client


def image_bytes(fmt: str, size: tuple[int, int] = (80, 60), frames: int = 1) -> bytes:
    images = [Image.new("RGB", size, (i * 60, 100, 200)) for i in range(frames)]
    buffer = io.BytesIO()
    images[0].save(buffer, format=fmt, save_all=frames > 1, append_images=images[1:])
    return buffer.getvalue()


def ctx(locale: str = "en-US") -> Any:
    context = make_ctx(locale=locale)
    context.defer = AsyncMock()
    context.delete = AsyncMock()
    context.interaction.execute = AsyncMock()
    context.client.model = SimpleNamespace(http=object())
    return context


def message(content: str | None, **author: Any) -> SimpleNamespace:
    fields = {
        "username": "km_rin", "global_name": "Rin", "default_avatar_url": "https://cdn.example/default.png",
        "make_avatar_url": lambda **_: "https://cdn.example/avatar.png",
    }
    return SimpleNamespace(content=content, user_mentions={}, member=None, author=SimpleNamespace(**(fields | author)))


def png(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    assert image.format == "PNG"
    return image


def sent_image(context: Any) -> Image.Image:
    context.respond.assert_awaited_once()
    attachment = context.respond.await_args.kwargs["attachment"]
    assert isinstance(attachment, hikari.Bytes)
    return png(attachment.data)  # type: ignore[arg-type]


def failed_privately(context: Any, key: str) -> bool:
    context.delete.assert_awaited_once()
    context.interaction.execute.assert_awaited_once()
    args, kwargs = context.interaction.execute.await_args
    return args == (t(key, context.locale),) and kwargs == {"flags": hikari.MessageFlag.EPHEMERAL}


# Models


def test_dice_roll_stays_in_range() -> None:
    rolls = {DiceRoll.roll(6).value for _ in range(500)}
    assert rolls == {1, 2, 3, 4, 5, 6}
    with pytest.raises(ValueError):
        DiceRoll(sides=1, value=1)


@pytest.mark.parametrize(
    ("url", "breed"),
    [
        ("https://images.dog.ceo/breeds/setter-irish/n02100877_5925.jpg", "Irish Setter"),
        ("https://images.dog.ceo/breeds/pug/x.jpg", "Pug"),
        ("https://images.dog.ceo/elsewhere/x.jpg", None),
    ],
)
def test_dog_photo_reads_the_breed(url: str, breed: str | None) -> None:
    assert DogPhoto.from_api({"message": url, "status": "success"}) == DogPhoto(url=url, breed=breed)


@pytest.mark.parametrize("data", [{"status": "error", "message": "nope"}, {"status": "success", "message": "http://insecure"}, [], None])
def test_dog_photo_rejects_bad_responses(data: Any) -> None:
    with pytest.raises(ValueError):
        DogPhoto.from_api(data)


@pytest.mark.parametrize(
    ("request_", "url"),
    [
        (CatRequest(), "https://cataas.com/cat"),
        (CatRequest(gif=True), "https://cataas.com/cat/gif"),
        (CatRequest(says="hi/there?"), "https://cataas.com/cat/says/hi%2Fthere%3F"),
        (CatRequest(gif=True, says="olá mundo"), "https://cataas.com/cat/gif/says/ol%C3%A1%20mundo"),
    ],
)
def test_cat_urls(request_: CatRequest, url: str) -> None:
    assert request_.url == url


def test_clean_text_turns_markup_into_plain_text() -> None:
    names = {("user", 1): "Rin", ("role", 2): "Mods", ("channel", 3): "general"}
    text = "**Hey** <@1> <@!1> <@&2> <#3> <@9>  <:blob:123> <a:party:456> 😀👍🏽 ||secret|| `code` <t:0:R>\n\n  next   line "
    assert clean_text(text, lambda kind, i: names.get((kind, i))) == (
        "Hey @Rin @Rin @Mods #general @user :blob: :party: secret code 1970-01-01 00:00 UTC\n\nnext line"
    )


def test_clean_text_can_end_up_empty() -> None:
    assert clean_text("😀 🎉", lambda *_: None) == ""


# Images


def test_wrap_breaks_long_words_and_spaceless_text() -> None:
    font = _font(40)
    lines = wrap("short " + "x" * 200 + " 日本語のテキストもちゃんと折り返されるかどうか", font, 300)
    assert lines[0] == "short"
    assert all(font.getlength(line) <= 300 for line in lines)
    assert "".join(lines).replace(" ", "") == "short" + "x" * 200 + "日本語のテキストもちゃんと折り返されるかどうか"


def test_fit_text_shrinks_then_cuts_with_an_ellipsis() -> None:
    assert fit_text("Gotta go fast!", 600, 400, max_size=72, min_size=22).font.size == 72
    fitted = fit_text("word " * 2000, 600, 400, max_size=72, min_size=22)
    assert fitted.font.size == 22
    assert fitted.height <= 400
    assert fitted.lines[-1].endswith("…")


def test_render_sonic_keeps_the_template_size() -> None:
    assert png(render_sonic("Gotta go fast!")).size == (1190, 648)


@pytest.mark.parametrize("mode", ["RGB", "RGBA", "P"])
def test_render_quote_is_black_and_white(mode: str) -> None:
    buffer = io.BytesIO()
    Image.new(mode, (300, 300), (255, 0, 0, 0) if mode == "RGBA" else 128).save(buffer, format="PNG")
    image = png(render_quote(buffer.getvalue(), "i'm on energy saving mode", "brian", "brian"))
    assert (image.size, image.mode) == (QUOTE_SIZE, "L")
    if mode == "RGBA":  # fully transparent avatar: the left side stays black
        assert image.getpixel((10, 10)) == 0


def test_render_quote_without_avatar() -> None:
    assert png(render_quote(None, "hello", "Rin", "km_rin")).size == QUOTE_SIZE


# APIs


async def test_fetch_cat_skips_cats_it_cant_send(monkeypatch: pytest.MonkeyPatch) -> None:
    server_error = aiohttp.ClientResponseError(SimpleNamespace(real_url="x"), (), status=500)  # type: ignore[arg-type]
    read = AsyncMock(side_effect=[http.TooLargeError("big"), server_error, (b"gif", "image/gif")])
    monkeypatch.setattr(apis, "read_capped", read)
    assert await apis.fetch_cat(None, CatRequest(gif=True)) == CatImage(data=b"gif", content_type="image/gif")  # type: ignore[arg-type]
    assert read.await_count == 3


async def test_fetch_cat_gives_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(apis, "read_capped", AsyncMock(side_effect=http.TooLargeError("big")))
    with pytest.raises(http.TooLargeError):
        await apis.fetch_cat(None, CatRequest())  # type: ignore[arg-type]


async def test_fetch_cat_does_not_retry_client_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    not_found = aiohttp.ClientResponseError(SimpleNamespace(real_url="x"), (), status=404)  # type: ignore[arg-type]
    read = AsyncMock(side_effect=not_found)
    monkeypatch.setattr(apis, "read_capped", read)
    with pytest.raises(aiohttp.ClientResponseError):
        await apis.fetch_cat(None, CatRequest())  # type: ignore[arg-type]
    assert read.await_count == 1


# Registration


@pytest.mark.parametrize(
    ("attribute", "en", "pt"),
    [("Dog", "dog", "cachorro"), ("Cat", "cat", "gato"), ("Roll", "roll", "rolar"), ("Sonic", "sonic", "sonic"),
     ("sonic_message", "Sonic", "Sonic"), ("quote_message", "Make it a quote", "Transformar em citação")],
)
def test_commands_work_in_servers_and_dms(client: crescent.Client, attribute: str, en: str, pt: str) -> None:
    command = getattr(_commands(), attribute).metadata.app_command
    assert str_or_build_locale(command.name) == (en, {"pt-BR": pt})
    assert set(command.context_types) == EVERYWHERE


# Slash commands


async def test_dog(client: crescent.Client, monkeypatch: pytest.MonkeyPatch) -> None:
    photo = DogPhoto(url="https://images.dog.ceo/breeds/pug/x.jpg", breed="Pug")
    monkeypatch.setattr(_commands(), "fetch_dog", AsyncMock(return_value=photo))
    download = AsyncMock(return_value=image_bytes("JPEG"))
    monkeypatch.setattr(_commands(), "download", download)
    context = ctx("pt-BR")
    await _commands().Dog.metadata.callback(context)

    context.defer.assert_awaited_once()
    assert download.await_args.args[1] == photo.url
    embed: hikari.Embed = context.respond.await_args.kwargs["embed"]
    assert embed.title == t("commands.fun.dog.title", "pt-BR")
    # uploaded, not linked: Discord never has to fetch dog.ceo itself
    assert embed.image is not None and embed.image.filename == "dog.jpg"
    assert embed.footer is not None and embed.footer.text == t("commands.fun.dog.breed", "pt-BR", breed="Pug")


@pytest.mark.parametrize("error", [aiohttp.ClientConnectionError("down"), TimeoutError(), ValueError("bad json")])
async def test_dog_failure_is_private(client: crescent.Client, monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    monkeypatch.setattr(_commands(), "fetch_dog", AsyncMock(side_effect=error))
    context = ctx()
    await _commands().Dog.metadata.callback(context)
    context.respond.assert_not_awaited()
    assert failed_privately(context, "commands.fun.dog.error")


async def test_cat_says_cleaned_text(client: crescent.Client, monkeypatch: pytest.MonkeyPatch) -> None:
    fetch = AsyncMock(return_value=CatImage(data=image_bytes("GIF", frames=3), content_type="image/gif"))
    monkeypatch.setattr(_commands(), "fetch_cat", fetch)
    context = ctx()
    await _commands().Cat.metadata.callback(context, gif=True, says="**hi** 😀")

    assert fetch.await_args.args[1] == CatRequest(gif=True, says="hi")
    embed: hikari.Embed = context.respond.await_args.kwargs["embed"]
    assert embed.image is not None and embed.image.filename == "cat.gif"


async def test_cat_failure_is_private(client: crescent.Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_commands(), "fetch_cat", AsyncMock(side_effect=http.TooLargeError("big")))
    context = ctx()
    await _commands().Cat.metadata.callback(context)
    assert failed_privately(context, "commands.fun.cat.error")


async def test_roll(client: crescent.Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("random.randint", lambda _low, high: high)
    context = ctx("pt-BR")
    await _commands().Roll.metadata.callback(context, sides=20)
    context.respond.assert_awaited_once_with(t("commands.fun.roll.response", "pt-BR", value=20, sides=20))


async def test_sonic(client: crescent.Client) -> None:
    context = ctx()
    await _commands().Sonic.metadata.callback(context, text="Gotta go fast!")
    context.defer.assert_awaited_once()
    assert sent_image(context).size == (1190, 648)


async def test_sonic_needs_drawable_text(client: crescent.Client) -> None:
    context = ctx()
    await _commands().Sonic.metadata.callback(context, text="😀🎉")
    context.defer.assert_not_awaited()
    context.respond.assert_awaited_once_with(t("commands.fun.no_text", "en-US"), ephemeral=True)


# Message commands


@pytest.mark.parametrize("command", ["sonic_message", "quote_message"])
async def test_message_commands_need_text(client: crescent.Client, command: str) -> None:
    context = ctx()
    await getattr(_commands(), command).metadata.callback(context, message(None))
    context.defer.assert_not_awaited()
    context.respond.assert_awaited_once_with(t("commands.fun.no_text", "en-US"), ephemeral=True)


async def test_sonic_message(client: crescent.Client) -> None:
    context = ctx()
    await _commands().sonic_message.metadata.callback(context, message("hello there"))
    assert sent_image(context).size == (1190, 648)


async def test_quote_message(client: crescent.Client, monkeypatch: pytest.MonkeyPatch) -> None:
    avatar = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(avatar, format="PNG")
    download = AsyncMock(return_value=avatar.getvalue())
    monkeypatch.setattr(_commands(), "download", download)

    context = ctx()
    await _commands().quote_message.metadata.callback(context, message("i'm on energy saving mode"))

    assert download.await_args.args[1] == "https://cdn.example/avatar.png"
    image = sent_image(context)
    assert (image.size, image.mode) == (QUOTE_SIZE, "L")
    assert image.getpixel((10, QUOTE_SIZE[1] // 2)) == 255  # the white avatar is on the left


async def test_quote_message_without_avatar_still_works(client: crescent.Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_commands(), "download", AsyncMock(side_effect=aiohttp.ClientConnectionError("cdn down")))
    context = ctx()
    await _commands().quote_message.metadata.callback(context, message("hello", make_avatar_url=lambda **_: None))
    image = sent_image(context)
    assert image.getpixel((10, QUOTE_SIZE[1] // 2)) == 0


# Image edits (Deepfry, JPEG, Pixelate)


from commands.fun.edits import deepfry, jpegify, pixelate  # noqa: E402
from core.media import Animation, load  # noqa: E402


def photo(mode: str = "RGB", size: tuple[int, int] = (300, 200)) -> bytes:
    image = Image.new(mode, size, (40, 120, 200, 255) if mode == "RGBA" else (40, 120, 200))
    if mode == "RGBA":
        image.putpixel((0, 0), (0, 0, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def animated(frames: int = 4) -> bytes:
    images = [Image.new("RGB", (64, 64), (i * 50, 0, 0)) for i in range(frames)]
    buffer = io.BytesIO()
    images[0].save(buffer, format="GIF", save_all=True, append_images=images[1:], duration=60, loop=0)
    return buffer.getvalue()


def opened(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


@pytest.mark.parametrize(("source", "extension", "fmt"), [(photo(), "jpg", "JPEG"), (photo("RGBA"), "png", "PNG"), (animated(), "gif", "GIF")])
def test_deepfry_keeps_the_kind_of_image(source: bytes, extension: str, fmt: str) -> None:
    result = deepfry(load(source))
    assert result.extension == extension
    image = opened(result.data)
    assert image.format == fmt
    assert getattr(image, "n_frames", 1) == getattr(opened(source), "n_frames", 1)


def test_deepfry_cranks_up_saturation() -> None:
    before = Image.open(io.BytesIO(photo())).convert("HSV").getpixel((150, 100))
    after = opened(deepfry(load(photo())).data).convert("HSV").getpixel((150, 100))
    assert after[1] > before[1]  # type: ignore[index]


def test_jpegify_makes_a_tiny_jpeg_of_the_first_frame() -> None:
    result = jpegify(load(animated()))
    image = opened(result.data)
    assert (result.extension, image.format, image.size) == ("jpg", "JPEG", (64, 64))
    # big numbers in the quantization table mean coarse, low quality compression
    table = opened(jpegify(load(photo())).data).quantization[0]  # type: ignore[attr-defined]
    assert sum(table) / len(table) > 100


def test_pixelate_makes_blocks() -> None:
    gradient = Image.linear_gradient("L").resize((400, 400)).convert("RGB")
    buffer = io.BytesIO()
    gradient.save(buffer, format="PNG")
    result = pixelate(load(buffer.getvalue()))
    image = opened(result.data).convert("RGB")
    assert result.extension == "png" and image.size == (400, 400)
    block = round(400 / 40)
    assert image.getpixel((0, 0)) == image.getpixel((block - 1, block - 1))
    assert image.getpixel((0, 0)) != image.getpixel((0, 399))


def test_pixelate_keeps_gifs_animated() -> None:
    result = pixelate(load(animated(5)))
    assert result.extension == "gif" and opened(result.data).n_frames == 5


def test_effects_take_animations_directly() -> None:
    assert pixelate(Animation([Image.new("RGBA", (10, 10), "red")])).extension == "png"


# Finding the image in a message


def media(url: str, proxy: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(url=url, proxy_url=proxy)


def with_media(**overrides: Any) -> SimpleNamespace:
    fields: dict[str, Any] = {"attachments": [], "embeds": [], "stickers": []}
    return SimpleNamespace(**(fields | overrides))


@pytest.mark.parametrize(
    ("msg", "url"),
    [
        (with_media(attachments=[SimpleNamespace(media_type="text/plain", url="https://cdn/a.txt"), SimpleNamespace(media_type="image/png", url="https://cdn/b.png")]), "https://cdn/b.png"),
        (with_media(embeds=[SimpleNamespace(image=media("https://x/i.jpg", "https://proxy/i.jpg"), thumbnail=None)]), "https://proxy/i.jpg"),
        (with_media(embeds=[SimpleNamespace(image=None, thumbnail=media("https://x/t.png"))]), "https://x/t.png"),
        (with_media(stickers=[SimpleNamespace(format_type=hikari.StickerFormatType.LOTTIE, make_url=lambda: "lottie"), SimpleNamespace(format_type=hikari.StickerFormatType.PNG, make_url=lambda: "https://cdn/s.png")]), "https://cdn/s.png"),
        (with_media(attachments=[SimpleNamespace(media_type=None, url="https://cdn/x")]), None),
        (with_media(), None),
    ],
)
def test_message_image_url(client: crescent.Client, msg: Any, url: str | None) -> None:
    assert _commands().message_image_url(msg) == url


# The message commands


EDITS = [("deepfry_message", "Deepfry", "Fritar"), ("jpeg_message", "JPEG", "JPEG"), ("pixelate_message", "Pixelate", "Pixelar")]


@pytest.mark.parametrize(("attribute", "en", "pt"), EDITS)
def test_edit_commands_are_registered(client: crescent.Client, attribute: str, en: str, pt: str) -> None:
    command = getattr(_commands(), attribute).metadata.app_command
    assert str_or_build_locale(command.name) == (en, {"pt-BR": pt})
    assert set(command.context_types) == EVERYWHERE


@pytest.mark.parametrize(("attribute", "filename"), [("deepfry_message", "deepfried.jpg"), ("jpeg_message", "jpeg.jpg"), ("pixelate_message", "pixelated.png")])
async def test_edit_commands_post_the_result(client: crescent.Client, monkeypatch: pytest.MonkeyPatch, attribute: str, filename: str) -> None:
    monkeypatch.setattr(_commands(), "download", AsyncMock(return_value=photo()))
    context = ctx()
    msg = with_media(attachments=[SimpleNamespace(media_type="image/png", url="https://cdn/b.png")])
    await getattr(_commands(), attribute).metadata.callback(context, msg)

    context.defer.assert_awaited_once()
    attachment = context.respond.await_args.kwargs["attachment"]
    assert attachment.filename == filename


async def test_edit_needs_an_image(client: crescent.Client) -> None:
    context = ctx()
    await _commands().deepfry_message.metadata.callback(context, with_media())
    context.defer.assert_not_awaited()
    context.respond.assert_awaited_once_with(t("commands.fun.image_edit.no_image", "en-US"), ephemeral=True)


@pytest.mark.parametrize(
    ("download", "key"),
    [
        (AsyncMock(side_effect=http.TooLargeError("big")), "too_big"),
        (AsyncMock(return_value=b"<html>not an image</html>"), "not_an_image"),
        (AsyncMock(side_effect=aiohttp.ClientConnectionError("cdn down")), "download_failed"),
    ],
)
async def test_edit_failures_are_private(client: crescent.Client, monkeypatch: pytest.MonkeyPatch, download: AsyncMock, key: str) -> None:
    monkeypatch.setattr(_commands(), "download", download)
    context = ctx()
    msg = with_media(attachments=[SimpleNamespace(media_type="image/png", url="https://cdn/b.png")])
    await _commands().pixelate_message.metadata.callback(context, msg)
    context.respond.assert_not_awaited()
    assert failed_privately(context, f"commands.fun.image_edit.{key}")
