"""Reconciliation against a real PostgreSQL.

Set SAGE_TEST_DATABASE_URL to a disposable database to run these, e.g.
``postgresql+asyncpg://sage:sage@127.0.0.1:5432/sage_test``. Every test drops and
recreates all tables, so never point it at real data.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from conftest import OWNER_ID
from core.sync import GuildSync
from models.db import (
    Base,
    FavoritePlaylist,
    FavoriteTrack,
    Guild,
    GuildAutoRoleConfig,
    GuildWelcomeChannelConfig,
    Owner,
    User,
    UserConfig,
)
from models.snapshots import GuildSnapshot, MemberSnapshot, OwnerSnapshot

URL = os.environ.get("SAGE_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.database,
    pytest.mark.skipif(not URL, reason="SAGE_TEST_DATABASE_URL not set"),
]


@pytest.fixture
async def database() -> AsyncIterator[SimpleNamespace]:
    assert URL
    engine = create_async_engine(make_url(URL))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield SimpleNamespace(
        engine=engine, session=async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    )
    await engine.dispose()


@pytest.fixture
def sync(database: SimpleNamespace) -> GuildSync:
    return GuildSync(database, owner_id=OWNER_ID)  # type: ignore[arg-type]


def member(user_id: int, name: str | None = None, *, admin: bool = False) -> MemberSnapshot:
    return MemberSnapshot(user_id=user_id, display_name=name or f"user{user_id}", is_admin=admin)


def guild(guild_id: int, *members: MemberSnapshot, name: str = "Friends") -> GuildSnapshot:
    return GuildSnapshot(guild_id=guild_id, guild_name=name, members=members)


async def load_guild(session: AsyncSession, guild_id: int) -> Guild | None:
    return await session.scalar(
        select(Guild)
        .where(Guild.guild_id == guild_id)
        .options(
            selectinload(Guild.members), selectinload(Guild.admins), selectinload(Guild.config)
        )
    )


async def user_ids(session: AsyncSession) -> set[int]:
    return set(await session.scalars(select(User.user_id)))


async def test_full_sync_creates_guilds_users_configs_and_admins(
    sync: GuildSync, database: SimpleNamespace
) -> None:
    report = await sync.full_sync([guild(1, member(10, admin=True), member(11))], present={1})
    assert (report.guilds_added, report.users_added) == (1, 2)

    async with database.session() as session:
        stored = await load_guild(session, 1)
        assert stored is not None
        assert {u.user_id for u in stored.members} == {10, 11}
        assert {u.user_id for u in stored.admins} == {10}
        assert await session.scalar(select(func.count()).select_from(UserConfig)) == 2
        assert await session.get(GuildAutoRoleConfig, 1) is not None
        welcome = await session.get(GuildWelcomeChannelConfig, 1)
        assert welcome is not None and welcome.active is False and welcome.show_pfp_option is True


async def test_second_identical_sync_changes_nothing(sync: GuildSync) -> None:
    snapshot = guild(1, member(10), member(11))
    await sync.full_sync([snapshot], present={1})
    assert not await sync.full_sync([snapshot], present={1})


async def test_updates_are_applied(sync: GuildSync, database: SimpleNamespace) -> None:
    await sync.full_sync([guild(1, member(10, "old"))], present={1})
    report = await sync.full_sync([guild(1, member(10, "new", admin=True), name="Renamed")], present={1})
    assert (report.guilds_updated, report.users_updated, report.memberships_changed) == (1, 1, 1)
    async with database.session() as session:
        stored = await load_guild(session, 1)
        assert stored is not None and stored.guild_name == "Renamed"
        assert [u.display_name for u in stored.admins] == ["new"]


async def test_member_leaving_their_only_guild_is_purged(
    sync: GuildSync, database: SimpleNamespace
) -> None:
    await sync.full_sync([guild(1, member(10), member(11))], present={1})
    report = await sync.full_sync([guild(1, member(10))], present={1})
    assert report.users_removed == 1
    async with database.session() as session:
        assert await user_ids(session) == {10}
        assert await session.get(UserConfig, 11) is None  # cascaded


async def test_member_of_another_guild_survives(sync: GuildSync, database: SimpleNamespace) -> None:
    await sync.full_sync([guild(1, member(10)), guild(2, member(10))], present={1, 2})
    await sync.full_sync([guild(1), guild(2, member(10))], present={1, 2})
    async with database.session() as session:
        assert await user_ids(session) == {10}


async def test_users_with_favorites_are_kept(sync: GuildSync, database: SimpleNamespace) -> None:
    await sync.full_sync([guild(1, member(10))], present={1})
    async with database.session.begin() as session:
        session.add(
            FavoriteTrack(user_id=10, title="t", url="https://example.com/t", duration=1000, uploader="u")
        )
    report = await sync.full_sync([guild(1)], present={1})
    assert report.users_removed == 0
    async with database.session() as session:
        assert await user_ids(session) == {10}


async def test_guilds_sage_left_are_removed_but_unfetched_ones_kept(
    sync: GuildSync, database: SimpleNamespace
) -> None:
    await sync.full_sync([guild(1, member(10)), guild(2, member(20)), guild(3, member(30))], present={1, 2, 3})
    # Guild 2 failed to fetch (still present), guild 3 was left.
    report = await sync.full_sync([guild(1, member(10))], present={1, 2})
    assert report.guilds_removed == 1
    async with database.session() as session:
        assert set(await session.scalars(select(Guild.guild_id))) == {1, 2}
        assert await user_ids(session) == {10, 20}


async def test_remove_guild(sync: GuildSync, database: SimpleNamespace) -> None:
    await sync.full_sync([guild(1, member(10))], present={1})
    report = await sync.remove_guild(1, reason="test")
    assert (report.guilds_removed, report.users_removed) == (1, 1)
    async with database.session() as session:
        assert await session.get(Guild, 1) is None
    assert not await sync.remove_guild(1, reason="again")


async def test_owner_is_never_purged(sync: GuildSync, database: SimpleNamespace) -> None:
    await sync.full_sync([guild(1, member(OWNER_ID), member(10))], present={1})
    await sync.full_sync([guild(1)], present={1})
    async with database.session() as session:
        assert await user_ids(session) == {OWNER_ID}


async def test_inactive_filter_is_usable_in_select(database: SimpleNamespace, sync: GuildSync) -> None:
    await sync.full_sync([guild(1, member(10))], present={1})
    async with database.session.begin() as session:
        session.add(User(user_id=99, display_name="loner", config=UserConfig()))
    async with database.session() as session:
        inactive = set(await session.scalars(select(User.user_id).where(User.is_inactive())))
    assert inactive == {99}


async def test_sync_owner_replaces_previous_owner(sync: GuildSync, database: SimpleNamespace) -> None:
    await sync.sync_owner(OwnerSnapshot(owner_id=1, owner_name="old"))
    await sync.sync_owner(OwnerSnapshot(owner_id=2, owner_name="new"))
    await sync.sync_owner(OwnerSnapshot(owner_id=2, owner_name="renamed"))
    async with database.session() as session:
        owners = (await session.scalars(select(Owner))).all()
    assert [(o.owner_id, o.owner_name) for o in owners] == [(2, "renamed")]


async def test_users_with_favorite_playlists_are_kept(sync: GuildSync, database: SimpleNamespace) -> None:
    await sync.full_sync([guild(1, member(10))], present={1})
    async with database.session.begin() as session:
        session.add(FavoritePlaylist(user_id=10, title="p", url="https://example.com/p", count=12, uploader="u"))
    await sync.full_sync([guild(1)], present={1})
    async with database.session() as session:
        assert await user_ids(session) == {10}
        playlist = await session.scalar(select(FavoritePlaylist))
        assert playlist is not None and playlist.added_in is not None


async def test_favorites_are_deleted_with_their_user(database: SimpleNamespace) -> None:
    async with database.session.begin() as session:
        session.add(
            User(
                user_id=50,
                display_name="x",
                config=UserConfig(),
                favorite_tracks=[FavoriteTrack(title="t", url="u", duration=1, uploader="u")],
                favorite_playlists=[FavoritePlaylist(title="p", url="u", uploader="u")],
            )
        )
    async with database.session.begin() as session:
        user = await session.get(User, 50)
        assert user is not None
        await session.delete(user)
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(FavoriteTrack)) == 0
        assert await session.scalar(select(func.count()).select_from(FavoritePlaylist)) == 0
