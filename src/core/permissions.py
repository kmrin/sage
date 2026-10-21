from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, overload

import crescent
import hikari

from core.i18n import tr
from core.logger import get_logger
from core.model import model_of

if TYPE_CHECKING:
    from crescent.internal.app_command import AppCommandMeta
    from crescent.internal.includable import Includable

    type Command = Includable[AppCommandMeta]

__all__ = ("guild_admin", "guild_only", "guild_specific", "owner_only")

type _Hook = Callable[[crescent.Context], Coroutine[Any, Any, crescent.HookResult | None]]

log = get_logger("Permissions")

_STOP = crescent.HookResult(exit=True)


async def _deny(ctx: crescent.Context, reason: str) -> crescent.HookResult:
    log.info(
        "Denied /%s for %s (%s) in %s: %s",
        ctx.command,
        ctx.user.username,
        ctx.user.id,
        ctx.guild_id or "DMs",
        reason,
    )
    await ctx.respond(tr(ctx, f"errors.permissions.{reason}"), ephemeral=True)
    return _STOP


def _is_owner(ctx: crescent.Context) -> bool:
    return ctx.user.id == model_of(ctx).settings.discord.owner_id


def _apply(hook: _Hook) -> Callable[[Command], Command]:
    def decorator(command: Command) -> Command:
        return crescent.hook(hook)(command)

    return decorator


async def _owner_hook(ctx: crescent.Context) -> crescent.HookResult | None:
    return None if _is_owner(ctx) else await _deny(ctx, "owner_only")


async def _guild_hook(ctx: crescent.Context) -> crescent.HookResult | None:
    return None if ctx.guild_id is not None else await _deny(ctx, "guild_only")


def owner_only(command: Command) -> Command:
    return _apply(_owner_hook)(command)


def guild_only(command: Command) -> Command:
    return _apply(_guild_hook)(command)


@overload
def guild_admin(command: Command, /) -> Command: ...
@overload
def guild_admin(*, allow_owner: bool = True) -> Callable[[Command], Command]: ...
def guild_admin(
    command: Command | None = None, /, *, allow_owner: bool = True
) -> Command | Callable[[Command], Command]:
    """
    Members with admin priviledges in the current server
    @guild_admin
    @guild_admin(allow_owner=False)
    """

    async def hook(ctx: crescent.Context) -> crescent.HookResult | None:
        if ctx.member is None or ctx.guild_id is None:
            return await _deny(ctx, "guild_only")
        if allow_owner and _is_owner(ctx):
            return None

        permissions = getattr(ctx.member, "permissions", hikari.Permissions.NONE)
        if permissions & hikari.Permissions.ADMINISTRATOR:
            return None

        return await _deny(ctx, "guild_admin")

    decorator = _apply(hook)
    return decorator(command) if command is not None else decorator


def guild_specific(*guild_ids: int) -> Callable[[Command], Command]:
    if not guild_ids:
        raise ValueError("guild_specific() needs at least one guild ID")

    allowed = frozenset(guild_ids)

    async def hook(ctx: crescent.Context) -> crescent.HookResult | None:
        if ctx.guild_id is None:
            return await _deny(ctx, "guild_only")
        return None if ctx.guild_id in allowed else await _deny(ctx, "guild_restricted")

    return _apply(hook)
