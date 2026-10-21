from __future__ import annotations

import functools
from typing import Annotated, Any

import hikari
from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

__all__ = (
    "DatabaseSettings",
    "DiscordSettings",
    "LavalinkSettings",
    "Settings",
    "SettingsError",
    "Snowflake",
    "get_settings",
)

Snowflake = Annotated[int, Field(gt=0, lt=2**63)]


def _blank_to_none(value: Any) -> Any:
    return None if isinstance(value, str) and not value.strip() else value


class _Base(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
        frozen=True,
        case_sensitive=False,
        hide_input_in_errors=True,
    )


class DatabaseSettings(_Base):
    model_config = SettingsConfigDict(env_prefix="POSTGRES_")

    host: str = "localhost"
    port: int = Field(default=5432, gt=0, lt=65536)
    db: str = "sage"
    user: str = "sage"
    password: SecretStr
    pool_size: int = Field(default=5, ge=1)
    max_overflow: int = Field(default=10, ge=0)

    @property
    def url(self) -> URL:
        return URL.create(
            "postgresql+asyncpg",
            username=self.user,
            password=self.password.get_secret_value(),
            host=self.host,
            port=self.port,
            database=self.db,
        )


class LavalinkSettings(_Base):
    model_config = SettingsConfigDict(env_prefix="LAVALINK_")

    host: str = "localhost"
    port: int = Field(default=2333, gt=0, lt=65536)
    password: SecretStr
    ssl: bool = False


class DiscordSettings(_Base):
    model_config = SettingsConfigDict(env_prefix="DISCORD_")

    token: SecretStr
    owner_id: Snowflake
    message_content_intent: bool = True

    @field_validator("token")
    @classmethod
    def _token_not_blank(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("DISCORD_TOKEN is empty")
        return value

    @property
    def intents(self) -> hikari.Intents:
        intents = hikari.Intents.ALL_UNPRIVILEGED | hikari.Intents.GUILD_MEMBERS
        if self.message_content_intent:
            intents |= hikari.Intents.MESSAGE_CONTENT
        return intents


class Settings(_Base):
    model_config = SettingsConfigDict(env_prefix="SAGE_")

    version: str = "0.0.0"
    debug: bool = False
    default_locale: str = "en-US"
    dev_guild_id: Snowflake | None = None

    discord: DiscordSettings
    database: DatabaseSettings
    lavalink: LavalinkSettings

    _blank_dev_guild = field_validator("dev_guild_id", mode="before")(_blank_to_none)

    @field_validator("default_locale")
    @classmethod
    def _known_locale(cls, value: str) -> str:
        locale = hikari.Locale(value)
        if not isinstance(locale, hikari.Locale):
            raise ValueError(f"{value!r} is not a Discord locale code (e.g. en-US, pt-BR)")
        return str(locale)


class SettingsError(ValueError):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("Invalid configuration:\n " + "\n ".join(problems))
        self.problems = problems


def _describe(error: ValidationError, model: type[_Base]) -> list[str]:
    prefix = str(model.model_config.get("env_prefix", ""))
    problems: list[str] = []
    for item in error.errors(include_url=False):
        variable = prefix + "_".join(str(part) for part in item["loc"]).upper()
        problems.append(f"{variable}: {item['msg']}")
    return problems


@functools.cache
def get_settings() -> Settings:
    problems: list[str] = []
    groups: dict[str, _Base] = {}

    for name, model in (
        ("discord", DiscordSettings),
        ("database", DatabaseSettings),
        ("lavalink", LavalinkSettings),
    ):
        try:
            groups[name] = model()  # pyright: ignore[reportCallIssue]
        except ValidationError as error:
            problems += _describe(error, model)
            groups[name] = model.model_construct()

    settings: Settings | None = None

    try:
        settings = Settings(**groups)  # pyright: ignore[reportArgumentType]
    except ValidationError as error:
        problems += _describe(error, Settings)

    if problems or settings is None:
        raise SettingsError(problems)

    return settings
