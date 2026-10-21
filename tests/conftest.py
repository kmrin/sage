from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from dotenv import dotenv_values

_ENV_FILE = Path(__file__).parents[1] / ".env"
if _ENV_FILE.is_file() and (_url := dotenv_values(_ENV_FILE).get("SAGE_TEST_DATABASE_URL")):
    os.environ.setdefault("SAGE_TEST_DATABASE_URL", _url)

# Tests must never pick up a developer's real .env or write to /var/lib/sage.
os.environ.setdefault("DISCORD_TOKEN", "test-token")
os.environ.setdefault("DISCORD_OWNER_ID", "100000000000000001")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("LAVALINK_PASSWORD", "test")

from core.paths import Paths  # noqa: E402

OWNER_ID = int(os.environ["DISCORD_OWNER_ID"])


@pytest.fixture
def tmp_paths(tmp_path: Path) -> Paths:
    paths = Paths(home=tmp_path / "sage")
    paths.ensure()
    return paths


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    import logging

    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    for handler in list(root.handlers):
        if handler not in handlers:
            root.removeHandler(handler)
            handler.close()
    root.setLevel(level)


def make_ctx(
    *,
    user_id: int = 200,
    guild_id: int | None = 300,
    permissions: int = 0,
    locale: str = "en-US",
    guild_locale: str | None = None,
    owner_id: int = OWNER_ID,
) -> SimpleNamespace:
    """A stand-in for ``crescent.Context`` with just what Sage's hooks touch."""
    import hikari

    member = (
        None
        if guild_id is None
        else SimpleNamespace(permissions=hikari.Permissions(permissions))
    )
    settings = SimpleNamespace(discord=SimpleNamespace(owner_id=owner_id))
    return SimpleNamespace(
        user=SimpleNamespace(id=user_id, username=f"user{user_id}"),
        member=member,
        guild_id=guild_id,
        locale=locale,
        command="test",
        interaction=SimpleNamespace(guild_locale=guild_locale),
        client=SimpleNamespace(model=SimpleNamespace(settings=settings)),
        respond=AsyncMock(),
    )
