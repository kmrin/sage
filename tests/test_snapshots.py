from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any

import hikari
import pydantic
import pytest

from commands.core.models import Latency
from models.snapshots import GuildSnapshot, MemberSnapshot

GUILD, OWNER, ADMIN_ROLE, PLAIN_ROLE = 900, 1, 50, 51


def _member(user_id: int, *, roles: tuple[int, ...] = (), bot: bool = False) -> Any:
    user = SimpleNamespace(
        id=user_id, username=f"name{user_id}", global_name=None, is_bot=bot, make_avatar_url=lambda: None
    )
    return SimpleNamespace(id=user_id, user=user, role_ids=roles, is_bot=bot)


def _guild(everyone_permissions: int = 0) -> Any:
    role = lambda permissions: SimpleNamespace(permissions=hikari.Permissions(permissions))  # noqa: E731
    return SimpleNamespace(
        id=GUILD,
        name="Friends",
        owner_id=OWNER,
        make_icon_url=lambda: "https://cdn.example/icon.png",
        roles={
            GUILD: role(everyone_permissions),
            ADMIN_ROLE: role(hikari.Permissions.ADMINISTRATOR | hikari.Permissions.SEND_MESSAGES),
            PLAIN_ROLE: role(hikari.Permissions.SEND_MESSAGES),
        },
    )


def test_admins_are_owner_and_administrator_roles_and_bots_are_skipped() -> None:
    members = [_member(OWNER), _member(2, roles=(ADMIN_ROLE,)), _member(3, roles=(PLAIN_ROLE,)), _member(4, bot=True)]
    snapshot = GuildSnapshot.from_rest(_guild(), members)
    assert [m.user_id for m in snapshot.members] == [OWNER, 2, 3]
    assert snapshot.admin_ids == {OWNER, 2}


def test_administrator_on_everyone_makes_everyone_admin() -> None:
    snapshot = GuildSnapshot.from_rest(_guild(int(hikari.Permissions.ADMINISTRATOR)), [_member(3)])
    assert snapshot.admin_ids == {3}


def test_fakes_match_hikari_api() -> None:
    """The fakes above stand in for real hikari objects; keep them honest."""
    for cls, names in (
        (hikari.User, ("id", "username", "global_name", "is_bot", "make_avatar_url")),
        (hikari.Member, ("id", "user", "role_ids", "is_bot")),
        (hikari.RESTGuild, ("id", "name", "owner_id", "roles", "make_icon_url")),
    ):
        fields = {a.name for a in getattr(cls, "__attrs_attrs__", ())}
        missing = [n for n in names if n not in fields and not hasattr(cls, n)]
        assert not missing, f"{cls.__name__} lacks {missing}"


def test_display_name_prefers_global_name() -> None:
    plain = _member(7)
    named = _member(8)
    named.user.global_name = "Rin"
    snapshot = GuildSnapshot.from_rest(_guild(), [plain, named])
    assert [m.display_name for m in snapshot.members] == ["name7", "Rin"]
    assert snapshot.guild_icon_url == "https://cdn.example/icon.png"


def test_snapshots_are_validated_and_frozen() -> None:
    with pytest.raises(pydantic.ValidationError):
        MemberSnapshot(user_id=0, display_name="x")
    member = MemberSnapshot(user_id=5, display_name="x")
    with pytest.raises(pydantic.ValidationError):
        member.display_name = "y"  # type: ignore[misc]


def test_latency_model() -> None:
    assert Latency(seconds=0.0426).milliseconds == 43
    pending = Latency(seconds=math.nan)
    assert not pending.measured and pending.milliseconds is None
