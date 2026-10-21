from __future__ import annotations

import asyncio
from dataclasses import dataclass, fields
from typing import TYPE_CHECKING

import hikari
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from core.logger import get_logger
from models.db import Guild, GuildConfig, Owner, User, UserConfig
from models.snapshots import GuildSnapshot, MemberSnapshot, OwnerSnapshot

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable

    from sqlalchemy.ext.asyncio import AsyncSession

    from core.database import Database

__all__ = ("GuildSync", "SyncReport", "fetch_guild_snapshot", "fetch_snapshots")

log = get_logger("Database")
fetch_log = get_logger("Sync")

FETCH_CONCURRENCY = 4
RESYNC_DELAY = 5.0
_ID_CHUNK = 5000


@dataclass(slots=True)
class SyncReport:
    guilds_added: int = 0
    guilds_updated: int = 0
    guilds_removed: int = 0
    users_added: int = 0
    users_updated: int = 0
    users_removed: int = 0
    memberships_changed: int = 0

    def __bool__(self) -> bool:
        return any(getattr(self, f.name) for f in fields(self))

    def summary(self) -> str:
        return (
            f"guilds +{self.guilds_added} ~{self.guilds_updated} -{self.guilds_removed}, "
            f"users +{self.users_added} ~{self.users_updated} -{self.users_removed}, "
            f"membership changes {self.memberships_changed}"
        )


async def fetch_guild_snapshot(rest: hikari.api.RESTClient, guild_id: int) -> GuildSnapshot:
    guild = await rest.fetch_guild(guild_id)
    members = [member async for member in rest.fetch_members(guild_id)]
    snapshot = GuildSnapshot.from_rest(guild, members)
    fetch_log.debug(
        "Fetched %s (%s): %d members, %d admins",
        snapshot.guild_name,
        snapshot.guild_id,
        len(snapshot.members),
        len(snapshot.admin_ids),
    )
    return snapshot


async def fetch_snapshots(
    rest: hikari.api.RESTClient,
) -> tuple[list[GuildSnapshot], frozenset[int]]:
    present = frozenset([guild.id async for guild in rest.fetch_my_guilds()])
    fetch_log.info("Sage is in %d guild(s), fetching members", len(present))

    semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)

    async def fetch(guild_id: int) -> GuildSnapshot | None:
        async with semaphore:
            try:
                return await fetch_guild_snapshot(rest, guild_id)
            except hikari.ForbiddenError:
                fetch_log.error(
                    "Missing access to members of guild %s. Is the Server Members intent on?",
                    guild_id,
                )
            except hikari.HTTPError as error:
                fetch_log.error("Could not fetch guild %s: %s", guild_id, error)
            return None

    results = await asyncio.gather(*(fetch(guild_id) for guild_id in present))
    snapshots = [snapshot for snapshot in results if snapshot is not None]

    if len(snapshots) != len(present):
        fetch_log.warn(
            "%d guild(s) could not be fetched and will not be modified",
            len(present) - len(snapshots),
        )

    return snapshots, present


class GuildSync:
    __slots__ = ("_database", "_lock", "_owner_id", "_pending")

    def __init__(self, database: Database, *, owner_id: int) -> None:
        self._database = database
        self._owner_id = owner_id
        self._lock = asyncio.Lock()
        self._pending: dict[int, asyncio.Task[None]] = {}

    async def sync_owner(self, owner: OwnerSnapshot) -> None:
        async with self._lock, self._database.session.begin() as session:
            rows = (await session.scalars(select(Owner))).all()
            current = next((row for row in rows if row.owner_id == owner.owner_id), None)

            for row in rows:
                if row is not current:
                    log.info("Removed previous owner %s (%s)", row.owner_name, row.owner_id)
                    await session.delete(row)

            if current is None:
                session.add(Owner(owner_id=owner.owner_id, owner_name=owner.owner_name))
                log.info("Registered owner %s (%s)", owner.owner_name, owner.owner_id)

            elif current.owner_name != owner.owner_name:
                log.info(
                    "Updated owner %s: name %r -> %r",
                    owner.owner_id,
                    current.owner_name,
                    owner.owner_name,
                )
                current.owner_name = owner.owner_name

            else:
                log.info("Owner %s (%s) is up to date", owner.owner_name, owner.owner_id)

    async def full_sync(
        self, snapshots: Iterable[GuildSnapshot], present: Collection[int]
    ) -> SyncReport:
        snapshots = list(snapshots)
        report = SyncReport()

        async with self._lock, self._database.session.begin() as session:
            await self._apply(session, snapshots, report)
            stale = await session.scalars(select(Guild).where(Guild.guild_id.not_in(present)))

            for guild in stale:
                log.info(
                    "Removed guild %s (%s): Sage is no longer in it",
                    guild.guild_name,
                    guild.guild_id,
                )

                await session.delete(guild)
                report.guilds_removed += 1

            await session.flush()
            await self._purge_inactive(session, report)

        return report

    async def sync_guild(self, snapshot: GuildSnapshot) -> SyncReport:
        report = SyncReport()

        async with self._lock, self._database.session.begin() as session:
            await self._apply(session, [snapshot], report)
            await session.flush()
            await self._purge_inactive(session, report)

        if report:
            log.info("Synced guild %s: %s", snapshot.guild_name, report.summary())
        else:
            log.debug("Guild %s already up to date", snapshot.guild_name)

        return report

    async def remove_guild(self, guild_id: int, *, reason: str) -> SyncReport:
        report = SyncReport()
        self._cancel_pending(guild_id)

        async with self._lock, self._database.session.begin() as session:
            guild = await session.get(Guild, guild_id)

            if guild is None:
                log.warn("Asked to remove guild %s, but it isn't in the database", guild_id)
                return report

            log.info("Removed guild %s (%s): %s", guild.guild_name, guild_id, reason)

            await session.delete(guild)

            report.guilds_removed += 1

            await session.flush()
            await self._purge_inactive(session, report)

        return report

    def schedule_resync(
        self,
        rest: hikari.api.RESTClient,
        guild_id: int,
        *,
        reason: str,
        delay: float = RESYNC_DELAY,
    ) -> None:
        self._cancel_pending(guild_id)
        log.debug("Resync of guild %s scheduled in %.0fs (%s)", guild_id, delay, reason)
        self._pending[guild_id] = asyncio.create_task(
            self._delayed_resync(rest, guild_id, delay), name=f"resync-{guild_id}"
        )

    async def close(self) -> None:
        tasks = list(self._pending.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._pending.clear()

    def _cancel_pending(self, guild_id: int) -> None:
        if (task := self._pending.pop(guild_id, None)) is not None:
            task.cancel()

    async def _delayed_resync(
        self, rest: hikari.api.RESTClient, guild_id: int, delay: float
    ) -> None:
        try:
            await asyncio.sleep(delay)
            if self._pending.get(guild_id) is asyncio.current_task():
                del self._pending[guild_id]
            snapshot = await fetch_guild_snapshot(rest, guild_id)
            await self.sync_guild(snapshot)
        except asyncio.CancelledError:
            raise
        except hikari.NotFoundError:
            log.warning("Guild %s vanished before it could be resynced", guild_id)
        except Exception:
            log.exception("Resync of guild %s failed", guild_id)

    async def _apply(
        self, session: AsyncSession, snapshots: list[GuildSnapshot], report: SyncReport
    ) -> None:
        members: dict[int, MemberSnapshot] = {}

        for snapshot in snapshots:
            for member in snapshot.members:
                members[member.user_id] = member

        users = await self._upsert_users(session, members, report)
        ids = [snapshot.guild_id for snapshot in snapshots]

        existing = {
            guild.guild_id: guild
            for guild in await session.scalars(
                select(Guild)
                .where(Guild.guild_id.in_(ids))
                .options(selectinload(Guild.members), selectinload(Guild.admins))
            )
        }

        for snapshot in snapshots:
            guild = existing.get(snapshot.guild_id)

            if guild is None:
                guild = Guild(
                    guild_id=snapshot.guild_id,
                    guild_name=snapshot.guild_name,
                    guild_icon_url=snapshot.guild_icon_url,
                    config=GuildConfig.with_defaults(),
                    members=[],
                    admins=[],
                )
                session.add(guild)
                report.guilds_added += 1
                log.info(
                    "Added guild %s (%s) with %d member(s)",
                    snapshot.guild_name,
                    snapshot.guild_id,
                    len(snapshot.members),
                )
            else:
                changes = _diff(guild, snapshot, ("guild_name", "guild_icon_url"))
                if changes:
                    report.guilds_updated += 1
                    log.info("Updated guild %s: %s", snapshot.guild_id, ", ".join(changes))

            member_ids = [member.user_id for member in snapshot.members]
            report.memberships_changed += _set_collection(
                guild,
                "members",
                [users[i] for i in member_ids],
                joined="%s joined guild %s",
                left="%s left guild %s",
            )
            report.memberships_changed += _set_collection(
                guild,
                "admins",
                [users[i] for i in member_ids if i in snapshot.admin_ids],
                joined="%s is now an admin of guild %s",
                left="%s is no longer an admin of guild %s",
            )

    async def _upsert_users(
        self, session: AsyncSession, members: dict[int, MemberSnapshot], report: SyncReport
    ) -> dict[int, User]:
        users: dict[int, User] = {}
        ids = list(members)

        for start in range(0, len(ids), _ID_CHUNK):
            chunk = ids[start : start + _ID_CHUNK]

            for user in await session.scalars(select(User).where(User.user_id.in_(chunk))):
                users[user.user_id] = user

        for user_id, member in members.items():
            user = users.get(user_id)

            if user is None:
                user = User(
                    user_id=user_id,
                    display_name=member.display_name,
                    global_name=member.global_name,
                    avatar_url=member.avatar_url,
                    config=UserConfig(),
                )
                session.add(user)
                users[user_id] = user
                report.users_added += 1
                log.info("Added user %s (%s)", member.display_name, user_id)
                continue

            changes = _diff(user, member, ("display_name", "global_name", "avatar_url"))

            if changes:
                report.users_updated += 1
                log.info("Updated user %s: %s", user_id, ", ".join(changes))

        return users

    async def _purge_inactive(self, session: AsyncSession, report: SyncReport) -> None:
        rows = (
            await session.execute(
                select(User.user_id, User.display_name).where(
                    User.is_inactive(), User.user_id != self._owner_id
                )
            )
        ).all()

        if not rows:
            return

        for user_id, name in rows:
            log.info(
                "Removed inactive user %s (%s): no guilds, favorites or settings", name, user_id
            )

        ids = [user_id for user_id, _ in rows]

        await session.execute(
            delete(User).where(User.user_id.in_(ids)).execution_options(synchronize_session=False)
        )

        report.users_removed += len(ids)


def _diff(target: object, source: object, names: Iterable[str]) -> list[str]:
    changes: list[str] = []
    for name in names:
        old, new = getattr(target, name), getattr(source, name)
        if old != new:
            changes.append(f"{name} {_short(old)} -> {_short(new)}")
            setattr(target, name, new)
    return changes


def _short(value: object, limit: int = 48) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _set_collection(
    guild: Guild, attribute: str, wanted: list[User], *, joined: str, left: str
) -> int:
    current: list[User] = getattr(guild, attribute)
    current_ids = {user.user_id for user in current}
    wanted_ids = {user.user_id for user in wanted}

    if current_ids == wanted_ids:
        return 0

    for user in wanted:
        if user.user_id not in current_ids:
            log.info(joined, f"{user.display_name} ({user.user_id})", guild.guild_name)
    for user in current:
        if user.user_id not in wanted_ids:
            log.info(left, f"{user.display_name} ({user.user_id})", guild.guild_name)

    setattr(guild, attribute, wanted)
    return len(current_ids ^ wanted_ids)
