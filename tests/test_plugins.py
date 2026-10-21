from __future__ import annotations

from typing import Any

import crescent
import hikari
import pytest
from crescent.locale import str_or_build_locale

from conftest import make_ctx
from core.i18n import t
from core.loader import command_modules, event_modules, load_plugins


@pytest.fixture
def client() -> crescent.Client:
    bot = hikari.GatewayBot("MTAwMDAwMDAwMDAwMDAwMDAx.fake.token", banner=None, logs=None, suppress_optimization_warning=True, intents=hikari.Intents.ALL_UNPRIVILEGED | hikari.Intents.GUILD_MEMBERS)
    return crescent.Client(bot, model=None)


def test_discovers_command_categories_and_events() -> None:
    assert "commands.core.commands" in command_modules()
    assert {"events.errors", "events.guilds", "events.lifecycle"} <= set(event_modules())


def test_all_plugins_load(client: crescent.Client) -> None:
    assert load_plugins(client) == len(command_modules()) + len(event_modules())


def _ping() -> Any:
    from commands.core import commands

    return commands.Ping


def test_ping_is_registered_with_translations(client: crescent.Client) -> None:
    client.plugins.load("commands.core.commands")
    meta = _ping().metadata
    name, name_localizations = str_or_build_locale(meta.app_command.name)
    description, description_localizations = str_or_build_locale(meta.app_command.description)
    assert name == "ping"
    assert name_localizations == {"pt-BR": "ping"}
    assert description == t("commands.core.ping.description", "en-US")
    assert description_localizations == {"pt-BR": t("commands.core.ping.description", "pt-BR")}


async def test_ping_responds_with_latency(client: crescent.Client, monkeypatch: pytest.MonkeyPatch) -> None:
    client.plugins.load("commands.core.commands")
    monkeypatch.setattr(hikari.GatewayBot, "heartbeat_latency", property(lambda _: 0.0421))
    ctx = make_ctx(locale="pt-BR")
    await _ping().metadata.callback(ctx)
    ctx.respond.assert_awaited_once_with(t("commands.core.ping.response", "pt-BR", latency=42))


async def test_ping_before_first_heartbeat(client: crescent.Client) -> None:
    client.plugins.load("commands.core.commands")
    ctx = make_ctx()
    await _ping().metadata.callback(ctx)  # unstarted bot: latency is NaN
    ctx.respond.assert_awaited_once_with(t("commands.core.ping.response_pending", "en-US"), ephemeral=True)
