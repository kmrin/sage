from __future__ import annotations

from typing import Any

import crescent
import hikari
import pytest

from conftest import OWNER_ID, make_ctx
from core.i18n import t
from core.permissions import guild_admin, guild_only, guild_specific, owner_only

ADMIN = int(hikari.Permissions.ADMINISTRATOR)


def _command(*decorators: Any) -> Any:
    @crescent.command(name="probe", description="probe")
    async def probe(ctx: crescent.Context) -> None: ...

    command = probe
    for decorator in reversed(decorators):  # apply bottom-up, like stacked @decorators
        command = decorator(command)
    return command


async def _run(command: Any, ctx: Any) -> bool:
    """Run the hooks the way crescent does. True if the command would execute."""
    for hook in command.metadata.hooks:
        result = await hook(ctx)
        if result is not None and result.exit:
            return False
    return True


def _denied_with(ctx: Any, reason: str) -> bool:
    ctx.respond.assert_awaited_once()
    args, kwargs = ctx.respond.await_args
    return args[0] == t(f"errors.permissions.{reason}", ctx.locale) and kwargs == {"ephemeral": True}


async def test_owner_only() -> None:
    command = _command(owner_only)
    assert await _run(command, make_ctx(user_id=OWNER_ID))
    ctx = make_ctx(user_id=5)
    assert not await _run(command, ctx)
    assert _denied_with(ctx, "owner_only")


async def test_guild_only_blocks_dms() -> None:
    command = _command(guild_only)
    assert await _run(command, make_ctx(guild_id=1))
    ctx = make_ctx(guild_id=None)
    assert not await _run(command, ctx)
    assert _denied_with(ctx, "guild_only")


@pytest.mark.parametrize(
    ("ctx_kwargs", "allowed", "reason"),
    [
        ({"permissions": ADMIN}, True, None),
        ({"permissions": 0}, False, "guild_admin"),
        ({"permissions": 0, "user_id": OWNER_ID}, True, None),
        ({"guild_id": None}, False, "guild_only"),
    ],
)
async def test_guild_admin(ctx_kwargs: dict[str, Any], allowed: bool, reason: str | None) -> None:
    ctx = make_ctx(**ctx_kwargs)
    assert await _run(_command(guild_admin), ctx) is allowed
    if reason:
        assert _denied_with(ctx, reason)


async def test_guild_admin_can_exclude_the_owner() -> None:
    ctx = make_ctx(user_id=OWNER_ID, permissions=0)
    assert not await _run(_command(guild_admin(allow_owner=False)), ctx)


async def test_guild_specific() -> None:
    command = _command(guild_specific(10, 20))
    assert await _run(command, make_ctx(guild_id=20))
    ctx = make_ctx(guild_id=30, locale="pt-BR")
    assert not await _run(command, ctx)
    assert _denied_with(ctx, "guild_restricted")


def test_guild_specific_needs_ids() -> None:
    with pytest.raises(ValueError):
        guild_specific()


async def test_checks_run_top_to_bottom_and_stop_at_first_failure() -> None:
    # Not the owner AND in DMs: the top decorator (guild_only) must answer.
    ctx = make_ctx(user_id=5, guild_id=None)
    assert not await _run(_command(guild_only, owner_only), ctx)
    assert _denied_with(ctx, "guild_only")

    ctx = make_ctx(user_id=5, guild_id=None)
    assert not await _run(_command(owner_only, guild_only), ctx)
    assert _denied_with(ctx, "owner_only")
