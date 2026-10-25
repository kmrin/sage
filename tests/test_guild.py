from __future__ import annotations

import os
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import crescent
import hikari
import pytest
from crescent.locale import str_or_build_locale
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from conftest import OWNER_ID, make_ctx
from commands.guild.models import WELCOME_COLOR, WelcomeValues, parse_color
from commands.guild.welcome import welcome_embed
from core.i18n import t
from core.sync import GuildSync
from models.db import Base, GuildAutoRoleConfig, GuildWelcomeChannelConfig
from models.snapshots import GuildSnapshot

GUILD_ID = 300
URL = os.environ.get("SAGE_TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not URL, reason="SAGE_TEST_DATABASE_URL not set")
VALUES = WelcomeValues(user="<@200>", username="Alice", server="Friends", member_count="42")


def _commands() -> Any:
    from commands.guild import commands

    return commands


def _events() -> Any:
    from commands.guild import events

    return events


@pytest.fixture
def client() -> crescent.Client:
    bot = hikari.GatewayBot("MTAwMDAwMDAwMDAwMDAwMDAx.fake.token", banner=None, logs=None, suppress_optimization_warning=True, intents=hikari.Intents.ALL_UNPRIVILEGED | hikari.Intents.GUILD_MEMBERS)
    client = crescent.Client(bot, model=None)
    client.plugins.load("commands.guild.commands")
    client.plugins.load("commands.guild.events")
    return client


@pytest.fixture
async def database() -> AsyncIterator[SimpleNamespace]:
    assert URL
    engine = create_async_engine(make_url(URL))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield SimpleNamespace(engine=engine, session=async_sessionmaker(engine, expire_on_commit=False, autoflush=False))
    await engine.dispose()


@pytest.fixture
async def synced(database: SimpleNamespace) -> SimpleNamespace:
    """The guild as core.sync leaves it: a guild row with default configs."""
    await GuildSync(database, owner_id=OWNER_ID).sync_guild(GuildSnapshot(guild_id=GUILD_ID, guild_name="Friends"))  # type: ignore[arg-type]
    return database


@pytest.fixture(autouse=True)
def _no_guild_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    for module in (_commands(), _events()):
        monkeypatch.setattr(module, "welcome_values", AsyncMock(return_value=(VALUES, "en-US")))


def member(**overrides: Any) -> SimpleNamespace:
    fields = {
        "id": 200, "guild_id": GUILD_ID, "mention": "<@200>", "display_name": "Alice", "username": "alice",
        "display_avatar_url": "https://cdn.example/avatar.png", "is_bot": False, "add_role": AsyncMock(),
    }
    return SimpleNamespace(**(fields | overrides))


def role(role_id: int = 777, **overrides: Any) -> SimpleNamespace:
    fields = {"id": role_id, "name": "Members", "mention": f"<@&{role_id}>", "is_managed": False, "position": 1}
    return SimpleNamespace(**(fields | overrides))


def admin_ctx(database: SimpleNamespace | None = None, locale: str = "en-US") -> Any:
    ctx = make_ctx(guild_id=GUILD_ID, locale=locale)
    ctx.member = member()
    ctx.client.model = SimpleNamespace(database=database)
    return ctx


def responded(ctx: Any) -> tuple[str, dict[str, Any]]:
    ctx.respond.assert_awaited_once()
    args, kwargs = ctx.respond.await_args
    return args[0], kwargs


async def welcome_row(database: SimpleNamespace) -> GuildWelcomeChannelConfig:
    async with database.session() as session:
        row = await session.get(GuildWelcomeChannelConfig, GUILD_ID)
    assert row is not None
    return row


async def auto_role_row(database: SimpleNamespace) -> GuildAutoRoleConfig:
    async with database.session() as session:
        row = await session.get(GuildAutoRoleConfig, GUILD_ID)
    assert row is not None
    return row


# Models


@pytest.mark.parametrize(("text", "value"), [("#9B59B6", 0x9B59B6), ("9b59b6", 0x9B59B6), ("#fff", 0xFFFFFF), (" #000000 ", 0)])
def test_parse_color(text: str, value: int) -> None:
    assert parse_color(text) == hikari.Color(value)


@pytest.mark.parametrize("text", ["purple", "#12345", "#GGGGGG", "", "#1234567"])
def test_parse_color_rejects_garbage(text: str) -> None:
    with pytest.raises(ValueError, match="hex color"):
        parse_color(text)


def test_render_fills_placeholders_and_newlines() -> None:
    assert VALUES.render("Hi {user}!\\nYou're #{member_count} in {server}, {username}.") == "Hi <@200>!\nYou're #42 in Friends, Alice."


def test_render_leaves_everything_else_alone() -> None:
    assert VALUES.render("{user.__class__} {unknown} {0} {{user}} {") == "{user.__class__} {unknown} {0} {<@200>} {"


# Registration


@pytest.mark.parametrize(
    ("attribute", "en", "pt"),
    [("SetWelcomeChannel", "welcome_channel", "canal_boas_vindas"), ("SetAutoRole", "auto_role", "cargo_automatico")],
)
def test_commands_are_translated_and_admin_only(client: crescent.Client, attribute: str, en: str, pt: str) -> None:
    meta = getattr(_commands(), attribute).metadata
    name, localizations = str_or_build_locale(meta.app_command.name)
    assert (name, localizations) == (en, {"pt-BR": pt})
    assert meta.sub_group is None
    assert str_or_build_locale(meta.group.name) == ("set", {"pt-BR": "definir"})
    assert len(meta.hooks) == 1  # guild_admin


# Welcome embed


def test_welcome_embed_defaults_follow_the_guild_locale(client: crescent.Client) -> None:
    config = GuildWelcomeChannelConfig(show_pfp_option=True)
    embed = welcome_embed(config, member(), VALUES, "pt-BR")
    assert embed.title == t("commands.guild.set.welcome_channel.default_title", "pt-BR", **VALUES.as_mapping())
    assert embed.description == t("commands.guild.set.welcome_channel.default_message", "pt-BR", **VALUES.as_mapping())
    assert embed.color == WELCOME_COLOR
    assert embed.thumbnail is not None


def test_welcome_embed_uses_custom_text(client: crescent.Client) -> None:
    config = GuildWelcomeChannelConfig(embed_title="Yo {username}", embed_description="x" * 5000, embed_color=0x112233, show_pfp_option=False)
    embed = welcome_embed(config, member(), VALUES, "en-US")
    assert embed.title == "Yo Alice"
    assert embed.description == "x" * 4096
    assert embed.color == hikari.Color(0x112233)
    assert embed.thumbnail is None


# Role checks


def test_role_problem_basics(client: crescent.Client) -> None:
    check = _commands().SetAutoRole.metadata.owner.role_problem
    assert check(role(GUILD_ID), GUILD_ID) == "commands.guild.set.auto_role.problems.everyone"
    assert check(role(is_managed=True), GUILD_ID) == "commands.guild.set.auto_role.problems.managed"
    assert check(role(), GUILD_ID) is None  # Sage isn't cached: leave it to Discord


@pytest.mark.parametrize(
    ("permissions", "top_position", "problem"),
    [
        (hikari.Permissions.NONE, 5, "missing_permission"),
        (hikari.Permissions.MANAGE_ROLES, 1, "too_high"),
        (hikari.Permissions.ADMINISTRATOR, 5, None),
        (hikari.Permissions.MANAGE_ROLES, 5, None),
    ],
)
def test_role_problem_checks_sage_can_assign(
    client: crescent.Client, monkeypatch: pytest.MonkeyPatch, permissions: hikari.Permissions, top_position: int, problem: str | None
) -> None:
    top = SimpleNamespace(permissions=permissions, position=top_position)
    sage = SimpleNamespace(get_roles=lambda: [top], get_top_role=lambda: top)
    monkeypatch.setattr(hikari.GatewayBot, "get_me", lambda _: SimpleNamespace(id=1))
    monkeypatch.setattr(type(client.app.cache), "get_member", lambda *_: sage)
    monkeypatch.setattr(type(client.app.cache), "get_role", lambda *_: None)
    result = _commands().SetAutoRole.metadata.owner.role_problem(role(position=1), GUILD_ID)
    assert result == (problem and f"commands.guild.set.auto_role.problems.{problem}")


async def test_bad_color_is_rejected_before_touching_the_db(client: crescent.Client) -> None:
    ctx = admin_ctx(database=None)
    await _commands().SetWelcomeChannel.metadata.callback(ctx, color="purple")
    content, kwargs = responded(ctx)
    assert content == t("commands.guild.set.welcome_channel.invalid_color", "en-US", color="purple")
    assert kwargs == {"ephemeral": True}


# Commands against the database


@pytest.mark.database
@needs_db
@pytest.mark.parametrize("command", ["SetWelcomeChannel", "SetAutoRole"])
async def test_commands_wait_for_the_sync(client: crescent.Client, database: SimpleNamespace, command: str) -> None:
    ctx = admin_ctx(database)
    await getattr(_commands(), command).metadata.callback(ctx, channel=SimpleNamespace(id=555, name="hi"), role=role())
    assert responded(ctx) == (t("errors.guild.not_synced", "en-US"), {"ephemeral": True})


@pytest.mark.database
@needs_db
async def test_welcome_needs_a_channel(client: crescent.Client, synced: SimpleNamespace) -> None:
    ctx = admin_ctx(synced)
    await _commands().SetWelcomeChannel.metadata.callback(ctx, title="ignored")
    assert responded(ctx) == (t("commands.guild.set.welcome_channel.no_channel", "en-US"), {"ephemeral": True})
    row = await welcome_row(synced)
    assert (row.active, row.embed_title) == (False, None)


@pytest.mark.database
@needs_db
async def test_welcome_saves_and_previews(client: crescent.Client, synced: SimpleNamespace) -> None:
    ctx = admin_ctx(synced, locale="pt-BR")
    await _commands().SetWelcomeChannel.metadata.callback(
        ctx, channel=SimpleNamespace(id=555, name="welcome"), title="Hi {username}", message="Line\\nTwo {user}", color="#112233", show_avatar=False
    )

    content, kwargs = responded(ctx)
    assert content.startswith(t("commands.guild.set.welcome_channel.saved", "pt-BR", channel="<#555>"))
    assert kwargs["ephemeral"] is True
    preview: hikari.Embed = kwargs["embed"]
    assert (preview.title, preview.description, preview.color, preview.thumbnail) == ("Hi Alice", "Line\nTwo <@200>", hikari.Color(0x112233), None)

    row = await welcome_row(synced)
    assert (row.active, row.channel_id, row.channel_name, row.embed_title, row.embed_color, row.show_pfp_option) == (
        True, 555, "welcome", "Hi {username}", 0x112233, False,
    )


@pytest.mark.database
@needs_db
async def test_welcome_disable_and_reset(client: crescent.Client, synced: SimpleNamespace) -> None:
    command = _commands().SetWelcomeChannel.metadata.callback
    await command(admin_ctx(synced), channel=SimpleNamespace(id=555, name="welcome"), title="Custom", color="#112233")

    ctx = admin_ctx(synced)
    await command(ctx, enabled=False)
    assert responded(ctx) == (t("commands.guild.set.welcome_channel.disabled", "en-US"), {"ephemeral": True})
    row = await welcome_row(synced)
    assert (row.active, row.channel_id, row.embed_title) == (False, 555, "Custom")

    ctx = admin_ctx(synced)
    await command(ctx, reset=True)  # turning it back on reuses the saved channel
    row = await welcome_row(synced)
    assert (row.active, row.channel_id, row.embed_title, row.embed_color) == (True, 555, None, None)


@pytest.mark.database
@needs_db
async def test_auto_role_saves_and_disables(client: crescent.Client, synced: SimpleNamespace) -> None:
    command = _commands().SetAutoRole.metadata.callback

    ctx = admin_ctx(synced)
    await command(ctx)
    assert responded(ctx) == (t("commands.guild.set.auto_role.no_role", "en-US"), {"ephemeral": True})

    ctx = admin_ctx(synced)
    await command(ctx, role=role())
    assert responded(ctx) == (t("commands.guild.set.auto_role.saved", "en-US", role="<@&777>"), {"ephemeral": True})
    row = await auto_role_row(synced)
    assert (row.active, row.role_id, row.role_name) == (True, 777, "Members")

    ctx = admin_ctx(synced)
    await command(ctx, enabled=False)
    assert responded(ctx) == (t("commands.guild.set.auto_role.disabled", "en-US"), {"ephemeral": True})
    row = await auto_role_row(synced)
    assert (row.active, row.role_id) == (False, 777)

    ctx = admin_ctx(synced)
    await command(ctx)  # the saved role was deleted (it isn't in the cache)
    assert responded(ctx)[0] == t("commands.guild.set.auto_role.problems.gone", "en-US")


@pytest.mark.database
@needs_db
async def test_auto_role_refuses_unassignable_roles(client: crescent.Client, synced: SimpleNamespace) -> None:
    ctx = admin_ctx(synced)
    await _commands().SetAutoRole.metadata.callback(ctx, role=role(is_managed=True))
    assert responded(ctx)[0] == t("commands.guild.set.auto_role.problems.managed", "en-US", role="<@&777>")
    assert (await auto_role_row(synced)).active is False


# Member joins


@pytest.mark.database
@needs_db
async def test_member_join_gives_role_and_welcomes(
    client: crescent.Client, synced: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with synced.session.begin() as session:
        auto_role = await session.get(GuildAutoRoleConfig, GUILD_ID)
        welcome = await session.get(GuildWelcomeChannelConfig, GUILD_ID)
        assert auto_role and welcome
        auto_role.active, auto_role.role_id = True, 777
        welcome.active, welcome.channel_id, welcome.embed_title = True, 555, "Hi {username}"

    events = _events()
    client.model = SimpleNamespace(database=synced)
    create_message = AsyncMock()
    monkeypatch.setattr(type(client.app.rest), "create_message", create_message)

    newcomer = member()
    await events.on_member_join.metadata.callback(SimpleNamespace(member=newcomer, guild_id=GUILD_ID))

    newcomer.add_role.assert_awaited_once()
    assert newcomer.add_role.await_args.args == (777,)
    create_message.assert_awaited_once()
    assert create_message.await_args.args == (555,)
    assert create_message.await_args.kwargs["embed"].title == "Hi Alice"

    bot = member(is_bot=True)
    await events.on_member_join.metadata.callback(SimpleNamespace(member=bot, guild_id=GUILD_ID))
    bot.add_role.assert_not_awaited()
    create_message.assert_awaited_once()


@pytest.mark.database
@needs_db
async def test_member_join_survives_discord_errors(
    client: crescent.Client, synced: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with synced.session.begin() as session:
        auto_role = await session.get(GuildAutoRoleConfig, GUILD_ID)
        welcome = await session.get(GuildWelcomeChannelConfig, GUILD_ID)
        assert auto_role and welcome
        auto_role.active, auto_role.role_id = True, 777
        welcome.active, welcome.channel_id = True, 555

    client.model = SimpleNamespace(database=synced)
    forbidden = hikari.ForbiddenError("https://discord.com/api", {}, b"")
    create_message = AsyncMock(side_effect=forbidden)
    monkeypatch.setattr(type(client.app.rest), "create_message", create_message)

    newcomer = member(add_role=AsyncMock(side_effect=forbidden))
    await _events().on_member_join.metadata.callback(SimpleNamespace(member=newcomer, guild_id=GUILD_ID))
    create_message.assert_awaited_once()  # the failed role didn't stop the welcome


@pytest.mark.database
@needs_db
async def test_missing_feature_row_is_created_with_defaults(client: crescent.Client, synced: SimpleNamespace) -> None:
    async with synced.session.begin() as session:
        await session.delete(await session.get(GuildWelcomeChannelConfig, GUILD_ID))

    ctx = admin_ctx(synced)
    await _commands().SetWelcomeChannel.metadata.callback(ctx, channel=SimpleNamespace(id=555, name="welcome"))

    row = await welcome_row(synced)
    assert (row.active, row.channel_id, row.show_pfp_option) == (True, 555, True)
    assert responded(ctx)[1]["embed"].thumbnail is not None
