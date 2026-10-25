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
from commands.user.images import PET_FRAMES, PET_SIZE, render_petpet
from core.i18n import t

EVERYWHERE = {hikari.ApplicationContextType.GUILD, hikari.ApplicationContextType.BOT_DM}


def _commands() -> Any:
    from commands.user import commands

    return commands


@pytest.fixture
def client() -> crescent.Client:
    bot = hikari.GatewayBot("MTAwMDAwMDAwMDAwMDAwMDAx.fake.token", banner=None, logs=None, suppress_optimization_warning=True)
    client = crescent.Client(bot, model=None)
    client.plugins.load("commands.user.commands")
    return client


def user(user_id: int = 5, **overrides: Any) -> SimpleNamespace:
    fields = {
        "id": user_id, "username": "km_rin", "global_name": "Rin",
        "display_avatar_url": "https://cdn.example/avatars/5/a.png?size=4096",
        "default_avatar_url": "https://cdn.example/embed/avatars/0.png",
        "make_avatar_url": lambda **kw: f"https://cdn.example/avatars/5/a.{kw['file_format'].lower()}?size={kw['size']}",
    }
    return SimpleNamespace(**(fields | overrides))


def ctx(locale: str = "en-US") -> Any:
    context = make_ctx(locale=locale)
    context.member = None
    context.user = user(200, username="caller", global_name="Caller")
    context.defer = AsyncMock()
    context.delete = AsyncMock()
    context.interaction.execute = AsyncMock()
    context.client.model = SimpleNamespace(http=object())
    return context


def avatar_png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (300, 300), "blue").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.parametrize(("attribute", "en", "pt"), [("Avatar", "avatar", "avatar"), ("Banner", "banner", "banner"), ("Pet", "pet", "carinho")])
def test_commands_work_in_servers_and_dms(client: crescent.Client, attribute: str, en: str, pt: str) -> None:
    command = getattr(_commands(), attribute).metadata.app_command
    assert str_or_build_locale(command.name) == (en, {"pt-BR": pt})
    assert set(command.context_types) == EVERYWHERE
    assert [option.name for option in command.options] == ["member"]


# /avatar


async def test_avatar_of_someone_is_private(client: crescent.Client) -> None:
    context = ctx("pt-BR")
    await _commands().Avatar.metadata.callback(context, member=user())

    kwargs = context.respond.await_args.kwargs
    assert kwargs["ephemeral"] is True
    embed: hikari.Embed = kwargs["embed"]
    assert embed.title == t("commands.user.avatar.title", "pt-BR", name="Rin")
    assert embed.image is not None and embed.image.url == "https://cdn.example/avatars/5/a.png?size=4096"


async def test_avatar_defaults_to_yourself(client: crescent.Client) -> None:
    context = ctx()
    await _commands().Avatar.metadata.callback(context)
    assert context.respond.await_args.kwargs["embed"].title == t("commands.user.avatar.title", "en-US", name="Caller")


# /banner


@pytest.fixture
def fetch_user(client: crescent.Client, monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock()
    monkeypatch.setattr(type(client.app.rest), "fetch_user", mock)
    return mock


async def test_banner(client: crescent.Client, fetch_user: AsyncMock) -> None:
    fetch_user.return_value = SimpleNamespace(make_banner_url=lambda **_: "https://cdn.example/banners/5/b.png", accent_color=hikari.Color(0x123456))
    context = ctx()
    await _commands().Banner.metadata.callback(context, member=user())

    context.defer.assert_awaited_once_with(ephemeral=True)
    embed: hikari.Embed = context.respond.await_args.kwargs["embed"]
    assert embed.image is not None and embed.image.url == "https://cdn.example/banners/5/b.png"
    assert embed.color == hikari.Color(0x123456)


async def test_banner_falls_back_to_the_profile_color(client: crescent.Client, fetch_user: AsyncMock) -> None:
    fetch_user.return_value = SimpleNamespace(make_banner_url=lambda **_: None, accent_color=hikari.Color(0x123456))
    context = ctx()
    await _commands().Banner.metadata.callback(context, member=user())
    embed: hikari.Embed = context.respond.await_args.kwargs["embed"]
    assert embed.description == t("commands.user.banner.accent_only", "en-US", name="Rin", color="#123456")


async def test_no_banner(client: crescent.Client, fetch_user: AsyncMock) -> None:
    fetch_user.return_value = SimpleNamespace(make_banner_url=lambda **_: None, accent_color=None)
    context = ctx()
    await _commands().Banner.metadata.callback(context, member=user())
    context.respond.assert_awaited_once_with(t("commands.user.banner.none", "en-US", name="Rin"), ephemeral=True)


async def test_banner_fetch_failure(client: crescent.Client, fetch_user: AsyncMock) -> None:
    fetch_user.side_effect = hikari.NotFoundError("https://discord.com/api", {}, b"")
    context = ctx()
    await _commands().Banner.metadata.callback(context, member=user())
    context.respond.assert_awaited_once_with(t("commands.user.banner.error", "en-US"), ephemeral=True)


# /pet


def test_render_petpet() -> None:
    image = Image.open(io.BytesIO(render_petpet(avatar_png())))
    assert (image.format, image.size, image.n_frames) == ("GIF", PET_SIZE, PET_FRAMES)
    image.seek(5)
    frame = image.convert("RGBA")
    assert frame.getpixel((0, 0))[3] == 0  # transparent background
    blue = sum(1 for pixel in frame.get_flattened_data() if pixel[:3] == (0, 0, 255))
    assert blue > 2000  # the avatar shows under the hand


async def test_pet(client: crescent.Client, monkeypatch: pytest.MonkeyPatch) -> None:
    download = AsyncMock(return_value=avatar_png())
    monkeypatch.setattr(_commands(), "download", download)
    context = ctx()
    await _commands().Pet.metadata.callback(context, member=user())

    assert download.await_args.args[1] == "https://cdn.example/avatars/5/a.png?size=256"
    args, kwargs = context.respond.await_args
    assert args == (t("commands.user.pet.response", "en-US", author="Caller", target="Rin"),)
    assert kwargs["user_mentions"] is False
    assert Image.open(io.BytesIO(kwargs["attachment"].data)).n_frames == PET_FRAMES


async def test_pet_uses_the_server_avatar(client: crescent.Client, monkeypatch: pytest.MonkeyPatch) -> None:
    download = AsyncMock(return_value=avatar_png())
    monkeypatch.setattr(_commands(), "download", download)
    member = hikari.InteractionMember.__new__(hikari.InteractionMember)  # isinstance(member, Member)
    monkeypatch.setattr(hikari.InteractionMember, "make_guild_avatar_url", lambda self, **_: "https://cdn.example/guilds/1/a.png")
    monkeypatch.setattr(hikari.InteractionMember, "display_name", property(lambda self: "Rinny"))
    monkeypatch.setattr(hikari.InteractionMember, "id", property(lambda self: 5), raising=False)
    context = ctx()
    await _commands().Pet.metadata.callback(context, member=member)
    assert download.await_args.args[1] == "https://cdn.example/guilds/1/a.png"


async def test_pet_avatar_failure_is_private(client: crescent.Client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_commands(), "download", AsyncMock(side_effect=aiohttp.ClientConnectionError("down")))
    context = ctx()
    await _commands().Pet.metadata.callback(context, member=user())
    context.respond.assert_not_awaited()
    context.delete.assert_awaited_once()
    assert context.interaction.execute.await_args.args == (t("commands.user.pet.error", "en-US"),)
