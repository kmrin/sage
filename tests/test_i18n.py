from __future__ import annotations

import ast
from pathlib import Path

import hikari
import pytest

from conftest import make_ctx
from core.i18n import Catalog, LocaleError, LocaleKeys, Localized, catalog, t, tr

EN, PT = hikari.Locale.EN_US, hikari.Locale.PT_BR


def test_shipped_locales_load_and_match() -> None:
    cat = catalog()
    assert set(cat.locales) == {EN, PT}
    assert "commands.core.ping.response" in cat.keys


def test_localized_feeds_crescent() -> None:
    name = Localized("commands.core.ping.description")
    assert name.fallback == catalog().get("commands.core.ping.description", EN)
    assert set(name.build()) == {"pt-BR"}


def test_unknown_key_fails_at_decoration_time() -> None:
    with pytest.raises(LocaleError, match="Unknown locale key"):
        Localized("commands.core.ping.nope")


def test_locale_keys_helper() -> None:
    keys = LocaleKeys("commands.core.ping")
    assert keys("response") == "commands.core.ping.response"
    assert keys.localized("name").key == "commands.core.ping.name"


def test_tr_follows_user_then_guild_then_default() -> None:
    portuguese = t("commands.core.ping.response", PT, latency=5)
    english = t("commands.core.ping.response", EN, latency=5)
    assert tr(make_ctx(locale="pt-BR"), "commands.core.ping.response", latency=5) == portuguese
    # Spanish client in a Brazilian server -> guild language.
    assert tr(make_ctx(locale="es-ES", guild_locale="pt-BR"), "commands.core.ping.response", latency=5) == portuguese
    # Nothing supported -> default (en-US unless configured).
    assert tr(make_ctx(locale="ja", guild_locale="ko"), "commands.core.ping.response", latency=5) == english


def test_missing_placeholder_value_is_an_error() -> None:
    with pytest.raises(LocaleError, match="latency"):
        t("commands.core.ping.response", EN)


@pytest.mark.parametrize(
    ("en_table", "pt_table", "problem"),
    [
        ({"a.b": "x"}, {}, "missing key a.b"),
        ({"a.b": "x"}, {"a.b": "x", "extra": "y"}, "unknown key extra"),
        ({"a.b": "{value}"}, {"a.b": "{other}"}, "uses {other}"),
        ({"a.b": "x"}, {"a.b": "  "}, "is empty"),
        ({"a.b": "x"}, {"a.b": "{unclosed"}, "Malformed"),
    ],
)
def test_validation_catches_inconsistent_files(
    en_table: dict[str, str], pt_table: dict[str, str], problem: str
) -> None:
    with pytest.raises(LocaleError, match=problem):
        Catalog({EN: en_table, PT: pt_table})


def test_from_directory_rejects_unknown_locale_files(tmp_path: Path) -> None:
    (tmp_path / "en-US.toml").write_text('a = "x"\n', encoding="utf-8")
    (tmp_path / "klingon.toml").write_text('a = "x"\n', encoding="utf-8")
    with pytest.raises(LocaleError, match="not a Discord locale"):
        Catalog.from_directory(tmp_path)


@pytest.mark.parametrize(
    ("key", "text"),
    [
        ("commands.x.name", "Has Caps"),
        ("commands.x.name", "has space"),
        ("commands.x.name", "a" * 33),
        ("commands.x.description", "d" * 101),
        ("commands.x.label", "l" * 33),
    ],
)
def test_validation_enforces_discord_limits(key: str, text: str) -> None:
    with pytest.raises(LocaleError):
        Catalog({EN: {key: text}})


def test_context_menu_labels_may_have_spaces_and_caps() -> None:
    Catalog({EN: {"commands.x.label": "Add To Favorites"}})


def test_no_user_facing_literals_in_commands() -> None:
    """Every respond()/name=/description= in command modules must go through i18n."""
    commands = Path(__file__).parents[1] / "src" / "commands"
    offenders: list[str] = []
    for file in commands.rglob("commands.py"):
        tree = ast.parse(file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_respond = isinstance(func, ast.Attribute) and func.attr in {"respond", "edit", "followup"}
            literals = [arg for arg in node.args if isinstance(arg, ast.Constant) and isinstance(arg.value, str)] if is_respond else []
            literals += [
                kw.value
                for kw in node.keywords
                if kw.arg in {"name", "description", "content"}
                and isinstance(kw.value, (ast.Constant, ast.JoinedStr))
            ]
            offenders += [f"{file.name}:{lit.lineno}" for lit in literals]
    assert offenders == []
