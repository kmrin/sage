from __future__ import annotations

import hikari
import pytest

from models.settings import SettingsError, get_settings


@pytest.fixture(autouse=True)
def _fresh() -> None:
    get_settings.cache_clear()


def test_loads_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAGE_VERSION", "1.2.3")
    monkeypatch.setenv("SAGE_DEBUG", "true")
    monkeypatch.setenv("SAGE_DEV_GUILD_ID", "")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p@ss/word")
    settings = get_settings()
    assert (settings.version, settings.debug, settings.dev_guild_id) == ("1.2.3", True, None)
    # Special characters survive because the URL is built structurally.
    assert settings.database.url.password == "p@ss/word"
    assert settings.database.url.drivername == "postgresql+asyncpg"


def test_intents_follow_the_message_content_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_MESSAGE_CONTENT_INTENT", "false")
    intents = get_settings().discord.intents
    assert intents & hikari.Intents.GUILD_MEMBERS
    assert not intents & hikari.Intents.MESSAGE_CONTENT


def test_every_problem_is_reported_by_variable_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", " ")
    monkeypatch.delenv("DISCORD_OWNER_ID")
    monkeypatch.setenv("LAVALINK_PORT", "99999")
    monkeypatch.setenv("SAGE_DEFAULT_LOCALE", "klingon")
    with pytest.raises(SettingsError) as raised:
        get_settings()
    variables = {problem.split(":", 1)[0] for problem in raised.value.problems}
    assert variables == {"DISCORD_TOKEN", "DISCORD_OWNER_ID", "LAVALINK_PORT", "SAGE_DEFAULT_LOCALE"}


def test_token_never_appears_in_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_OWNER_ID", "not-a-number")
    monkeypatch.setenv("DISCORD_TOKEN", "super-secret-token")
    with pytest.raises(SettingsError) as raised:
        get_settings()
    assert "super-secret-token" not in str(raised.value)
