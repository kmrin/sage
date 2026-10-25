from __future__ import annotations

import io
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import hikari
import miru
import pytest
from miru.ext import nav
from PIL import Image, ImageDraw

from core import media
from core.http import TooLargeError
from core.i18n import t
from core.media import Animation, BadImageError, Encoded, encode_gif, fit_upload, load
from core.paginator import PaginatedResponse


def gif(frames: list[Image.Image], duration: int = 50) -> bytes:
    buffer = io.BytesIO()
    frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:], duration=duration, loop=0)
    return buffer.getvalue()


def png(size: tuple[int, int], color: Any = "red", mode: str = "RGB") -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, size, color).save(buffer, format="PNG")
    return buffer.getvalue()


# Loading


def test_load_still_image() -> None:
    animation = load(png((40, 30)))
    assert not animation.animated
    assert animation.frames[0].mode == "RGBA"
    assert animation.frames[0].size == (40, 30)


def test_load_gif_keeps_timing() -> None:
    frames = [Image.new("RGB", (8, 8), color) for color in ("red", "green", "blue")]
    animation = load(gif(frames, duration=70))
    assert animation.animated
    assert animation.durations == [70, 70, 70]
    assert [frame.getpixel((0, 0))[:3] for frame in animation.frames] == [(255, 0, 0), (0, 128, 0), (0, 0, 255)]


def test_load_shrinks_big_images() -> None:
    assert max(load(png((3200, 1600))).frames[0].size) == media.MAX_STILL_SIDE
    big_gif = gif([Image.new("RGB", (1024, 512), c) for c in ("red", "blue")])
    assert load(big_gif).frames[0].size == (media.MAX_ANIMATED_SIDE, media.MAX_ANIMATED_SIDE // 2)


def test_load_thins_out_long_gifs_without_changing_speed() -> None:
    frames = [Image.new("RGB", (4, 4), (i, 0, 0)) for i in range(250)]
    animation = load(gif(frames, duration=40))
    assert len(animation.frames) <= media.MAX_FRAMES
    assert sum(animation.durations) == 250 * 40


def test_load_rejects_garbage() -> None:
    with pytest.raises(BadImageError):
        load(b"definitely not an image")


# Saving


def test_encode_gif_keeps_transparency_and_clears_old_frames() -> None:
    frames = []
    for i in range(5):
        frame = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        ImageDraw.Draw(frame).rectangle((i * 10, 20, i * 10 + 9, 30), fill=(255, 0, 0, 255))
        frames.append(frame)

    back = load(encode_gif(Animation(frames, [50] * 5)))

    assert len(back.frames) == 5
    for i, frame in enumerate(back.frames):
        assert frame.getpixel((0, 0))[3] == 0  # see-through
        assert frame.getpixel((i * 10 + 4, 25)) == (255, 0, 0, 255)
        if i:  # no ghost of the previous frame's square
            assert frame.getpixel(((i - 1) * 10 + 2, 25))[3] == 0


def test_fit_upload_shrinks_until_it_fits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(media, "MAX_UPLOAD", 100)
    sizes: list[int] = []

    def encode(animation: Animation) -> Encoded:
        width = animation.frames[0].width
        sizes.append(width)
        return Encoded(b"x" * width, "png")

    assert fit_upload(Animation([Image.new("RGBA", (200, 200))]), encode).data == b"x" * 84
    assert sizes == [200, 150, 112, 84]


def test_fit_upload_gives_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(media, "MAX_UPLOAD", 0)
    with pytest.raises(TooLargeError):
        fit_upload(Animation([Image.new("RGBA", (10, 10))]), lambda _: Encoded(b"x", "png"))


# Paginator


@pytest.fixture
def bot() -> hikari.GatewayBot:
    return hikari.GatewayBot("MTAwMDAwMDAwMDAwMDAwMDAx.fake.token", banner=None, logs=None, suppress_optimization_warning=True)


@pytest.fixture
def start_view(monkeypatch: pytest.MonkeyPatch) -> Mock:
    mock = Mock()
    monkeypatch.setattr(miru.Client, "start_view", mock)  # Client uses slots
    return mock


def pages(count: int) -> list[hikari.Embed]:
    return [hikari.Embed(title=f"Page {i + 1}") for i in range(count)]


def ctx() -> Any:
    return SimpleNamespace(user=SimpleNamespace(id=1), respond=AsyncMock(return_value=SimpleNamespace(id=999)))


async def test_paginator_needs_pages() -> None:
    with pytest.raises(ValueError, match="at least one page"):
        PaginatedResponse([], owner_id=1)


async def test_paginator_buttons_in_order() -> None:
    view = PaginatedResponse(pages(3), owner_id=1)
    assert [type(item) for item in view.children] == [nav.FirstButton, nav.PrevButton, nav.IndicatorButton, nav.NextButton, nav.LastButton]
    assert [str(item.emoji) if item.emoji else None for item in view.children] == ["⏮️", "◀️", None, "▶️", "⏭️"]


@pytest.mark.parametrize(("user_id", "allowed"), [(1, True), (2, False)])
async def test_paginator_only_answers_the_owner(user_id: int, allowed: bool) -> None:
    view = PaginatedResponse(pages(2), owner_id=1)
    context = SimpleNamespace(user=SimpleNamespace(id=user_id), locale="pt-BR", respond=AsyncMock())
    assert await view.view_check(context) is allowed  # type: ignore[arg-type]
    if allowed:
        context.respond.assert_not_awaited()
    else:
        context.respond.assert_awaited_once_with(t("errors.paginator.not_yours", "pt-BR"), flags=hikari.MessageFlag.EPHEMERAL)


async def test_single_page_has_no_buttons(bot: hikari.GatewayBot, start_view: Mock) -> None:
    client = miru.Client(bot)
    context = ctx()
    only = pages(1)
    await PaginatedResponse(only, owner_id=1).send(context, client)

    kwargs = context.respond.await_args.kwargs
    assert kwargs["embeds"] == only
    assert kwargs["components"] is hikari.UNDEFINED
    start_view.assert_not_called()


async def test_multiple_pages_start_on_the_first_with_buttons(bot: hikari.GatewayBot, start_view: Mock) -> None:
    client = miru.Client(bot)
    context = ctx()
    many = pages(10)
    view = PaginatedResponse(many, owner_id=1)
    await view.send(context, client, ephemeral=True)

    kwargs = context.respond.await_args.kwargs
    assert kwargs["embeds"] == [many[0]]
    assert kwargs["ephemeral"] is True
    assert kwargs["components"]  # the button row
    indicator = next(item for item in view.children if isinstance(item, nav.IndicatorButton))
    assert indicator.label == "1/10"
    start_view.assert_called_once_with(view, bind_to=context.respond.return_value)
