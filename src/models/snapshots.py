from __future__ import annotations

from typing import TYPE_CHECKING

import hikari
from pydantic import BaseModel, ConfigDict, Field

from models.settings import Snowflake

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = ("GuildSnapshot", "MemberSnapshot", "OwnerSnapshot")


class _Snapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class OwnerSnapshot(_Snapshot):
    owner_id: Snowflake
    owner_name: str = Field(min_length=1, max_length=100)

    @classmethod
    def from_user(cls, user: hikari.User) -> OwnerSnapshot:
        return cls(owner_id=user.id, owner_name=user.username)


class MemberSnapshot(_Snapshot):
    user_id: Snowflake
    display_name: str = Field(min_length=1, max_length=100)
    global_name: str | None = Field(default=None, max_length=100)
    avatar_url: str | None = None
    is_admin: bool = False

    @classmethod
    def from_member(cls, member: hikari.Member, *, is_admin: bool) -> MemberSnapshot:
        user = member.user
        avatar = user.make_avatar_url()

        return cls(
            user_id=user.id,
            display_name=user.global_name or user.username,
            global_name=user.global_name,
            avatar_url=str(avatar) if avatar else None,
            is_admin=is_admin,
        )


class GuildSnapshot(_Snapshot):
    guild_id: Snowflake
    guild_name: str = Field(min_length=1, max_length=100)
    guild_icon_url: str | None = None
    members: tuple[MemberSnapshot, ...] = ()

    @classmethod
    def from_rest(cls, guild: hikari.RESTGuild, members: Iterable[hikari.Member]) -> GuildSnapshot:
        admin_roles = {
            role_id
            for role_id, role in guild.roles.items()
            if role.permissions & hikari.Permissions.ADMINISTRATOR
        }

        everyone_is_admin = guild.id in admin_roles
        snapshots: dict[int, MemberSnapshot] = {}

        for member in members:
            if member.is_bot:
                continue

            is_admin = (
                everyone_is_admin
                or member.id == guild.owner_id
                or not admin_roles.isdisjoint(member.role_ids)
            )

            snapshots[member.id] = MemberSnapshot.from_member(member, is_admin=is_admin)

        icon = guild.make_icon_url()

        return cls(
            guild_id=guild.id,
            guild_name=guild.name,
            guild_icon_url=str(icon) if icon else None,
            members=tuple(snapshots.values()),
        )

    @property
    def admin_ids(self) -> frozenset[int]:
        return frozenset(member.user_id for member in self.members if member.is_admin)
