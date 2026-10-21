"""
[commands.core.ping]
name = "ping"               -> "commands.core.ping.name"
resp = "Pong! {latency} ms" -> "commands.core.ping.response"
"""

from __future__ import annotations

import re
import string
import threading
import tomllib
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Final

import hikari
from crescent import LocaleBuilder

from core.paths import paths

if TYPE_CHECKING:
    from pathlib import Path

    import crescent

__all__ = (
    "FALLBACK_LOCALE",
    "Catalog",
    "LocaleError",
    "LocaleKeys",
    "Localized",
    "catalog",
    "configure",
    "discord_locale",
    "t",
    "tr",
)

FALLBACK_LOCALE: Final = hikari.Locale.EN_US

_SLASH_NAME: Final = re.compile(r"^[-_'\w]{1,32}$")
_formatter: Final = string.Formatter()


class LocaleError(RuntimeError):
    """A locale file is missing, malformed, or inconsistent with the others."""


class Catalog:
    __slots__ = ("_default", "_tables")

    def __init__(self, tables: Mapping[hikari.Locale, Mapping[str, str]]) -> None:
        if FALLBACK_LOCALE not in tables:
            raise LocaleError(f"Missing fallback locale file {FALLBACK_LOCALE}.toml")
        self._tables = {locale: dict(table) for locale, table in tables.items()}
        self._default = FALLBACK_LOCALE
        _validate(self._tables)

    @classmethod
    def from_directory(cls, directory: Path) -> Catalog:
        tables: dict[hikari.Locale, dict[str, str]] = {}

        for file in sorted(directory.glob("*.toml")):
            locale = discord_locale(file.stem)

            if locale is None:
                raise LocaleError(f"{file.name}: '{file.stem}' is not a Discord locale")

            try:
                with file.open("rb") as handle:
                    tables[locale] = _flatten(tomllib.load(handle), file.name)
            except tomllib.TOMLDecodeError as error:
                raise LocaleError(f"{file.name}: invlaid TOML ({error})") from error

            if not tables:
                raise LocaleError(f"No locale files found in {directory}")

        return cls(tables)

    @property
    def locales(self) -> tuple[hikari.Locale, ...]:
        return tuple(self._tables)

    @property
    def default(self) -> hikari.Locale:
        return self._default

    @default.setter
    def default(self, locale: hikari.Locale) -> None:
        if locale not in self._tables:
            raise LocaleError(f"{locale} has no locale file")
        self._default = locale

    @property
    def keys(self) -> frozenset[str]:
        return frozenset(self._tables[FALLBACK_LOCALE])

    def has(self, key: str) -> bool:
        return key in self._tables[FALLBACK_LOCALE]

    def supports(self, locale: str | hikari.Locale | None) -> bool:
        return self._coerce(locale) is not None

    def resolve(self, *candidates: str | hikari.Locale | None) -> hikari.Locale:
        for candidate in candidates:
            if (locale := self._coerce(candidate)) is not None:
                return locale
        return self._default

    def get(self, key: str, locale: str | hikari.Locale | None = None) -> str:
        try:
            return self._tables[self.resolve(locale)][key]
        except KeyError:
            raise LocaleError(f"Unknown locale key {key!r}") from None

    def format(self, key: str, locale: str | hikari.Locale | None = None, **values: object) -> str:
        template = self.get(key, locale)
        try:
            return template.format_map(values)
        except (KeyError, IndexError) as error:
            raise LocaleError(f"{key!r} expects placeholder {error}") from error

    def localizations(self, key: str) -> dict[str, str]:
        self.get(key)
        return {
            str(locale): table[key]
            for locale, table in self._tables.items()
            if locale != FALLBACK_LOCALE
        }

    def _coerce(self, value: str | hikari.Locale | None) -> hikari.Locale | None:
        locale = discord_locale(value)
        return locale if locale in self._tables else None


def discord_locale(value: str | hikari.Locale | None) -> hikari.Locale | None:
    if value is None:
        return None
    locale = hikari.Locale(value)
    return locale if isinstance(locale, hikari.Locale) else None


class Localized(LocaleBuilder):
    __slots__ = ("key",)

    def __init__(self, key: str) -> None:
        if not catalog().has(key):
            raise LocaleError(f"Unknown locale key {key!r}")
        self.key = key

    def __repr__(self) -> str:
        return f"Localized({self.key!r})"

    @property
    def fallback(self) -> str:
        return catalog().get(self.key, FALLBACK_LOCALE)

    def build(self) -> Mapping[str, str]:
        return catalog().localizations(self.key)


class LocaleKeys:
    __slots__ = ("prefix",)

    def __init__(self, prefix: str) -> None:
        self.prefix = prefix.rstrip(".")

    def __call__(self, suffix: str) -> str:
        return f"{self.prefix}.{suffix}"

    def localized(self, suffix: str) -> Localized:
        return Localized(self(suffix))

    def child(self, suffix: str) -> LocaleKeys:
        return LocaleKeys(self(suffix))


_catalog: Catalog | None = None
_catalog_lock = threading.Lock()


def catalog() -> Catalog:
    global _catalog  # noqa: PLW0603
    if _catalog is None:
        with _catalog_lock:
            if _catalog is None:
                _catalog = Catalog.from_directory(paths.locales)
    return _catalog


def configure(default_locale: str) -> hikari.Locale:
    cat = catalog()
    cat.default = cat.resolve(default_locale, FALLBACK_LOCALE)
    return cat.default


def t(key: str, locale: str | hikari.Locale | None = None, /, **values: object) -> str:
    return catalog().format(key, locale, **values)


def tr(ctx: crescent.Context | crescent.AutocompleteContext, key: str, /, **values: object) -> str:
    guild_locale = getattr(ctx.interaction, "guild_locale", None)
    return catalog().format(key, catalog().resolve(ctx.locale, guild_locale), **values)


def _flatten(table: Mapping[str, Any], source: str, prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for name, value in table.items():
        key = f"{prefix}{name}"
        if isinstance(value, Mapping):
            flat.update(_flatten(value, source, f"{key}."))
        elif isinstance(value, str):
            flat[key] = value
        else:
            raise LocaleError(f"{source}: {key} must be a string, got {type(value).__name__}")
    return flat


def _placeholders(template: str) -> frozenset[str]:
    try:
        return frozenset(field for _, field, _, _ in _formatter.parse(template) if field)
    except ValueError as error:
        raise LocaleError(f"Malformed template {template!r}: {error}") from error


def _validate(tables: Mapping[hikari.Locale, Mapping[str, str]]) -> None:
    problems: list[str] = []
    reference = tables[FALLBACK_LOCALE]

    for locale, table in tables.items():
        if locale != FALLBACK_LOCALE:
            missing = reference.keys() - table.keys()
            unknown = table.keys() - reference.keys()
            problems.extend(f"{locale}: missing key {key}" for key in sorted(missing))
            problems.extend(f"{locale}: unknown key {key}" for key in sorted(unknown))

        for key, text in table.items():
            if not text.strip():
                problems.append(f"{locale}: {key} is empty")
                continue

            try:
                fields = _placeholders(text)
                expected = _placeholders(reference[key]) if key in reference else fields
            except LocaleError as error:
                problems.append(f"{locale}: {key}: {error}")
                continue

            if fields != expected:
                problems.append(
                    f"{locale}: {key} uses {{{', '.join(sorted(fields))}}}, "
                    f"{FALLBACK_LOCALE} uses {{{', '.join(sorted(expected))}}}"
                )

            problems.extend(f"{locale}: {issue}" for issue in _discord_limits(key, text))

    if problems:
        raise LocaleError("Locale validation failed:\n " + "\n ".join(problems))


def _discord_limits(key: str, text: str) -> list[str]:
    if not key.startswith("commands."):
        return []

    leaf = key.rsplit(".", 1)[-1]

    if leaf == "name" and (not _SLASH_NAME.fullmatch(text) or text != text.lower()):
        return [f"{key} = {text!r}: slash names must be lowercase, no spaces, 1-32 chars"]
    if leaf == "label" and not 1 <= len(text) <= 32:
        return [f"{key}: context menu names must be 1-32 chars"]
    if leaf == "description" and not 1 <= len(text) <= 100:
        return [f"{key}: descriptions must be 1-100 chars (has {len(text)})"]

    return []
