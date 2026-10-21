from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    ColumnElement,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    and_,
    false,
    func,
    or_,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

__all__ = (
    "Base",
    "FavoritePlaylist",
    "FavoriteTrack",
    "Guild",
    "GuildAutoRoleConfig",
    "GuildConfig",
    "GuildWelcomeChannelConfig",
    "Owner",
    "User",
    "UserConfig",
    "guild_admins",
    "guild_members",
)

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        datetime: DateTime(timezone=True),
    }


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


def _snowflake_fk(target: str) -> Mapped[int]:
    return mapped_column(BigInteger, ForeignKey(target, ondelete="CASCADE"), primary_key=True)


guild_members = Table(
    "guild_members",
    Base.metadata,
    Column(
        "guild_id", BigInteger, ForeignKey("guilds.guild_id", ondelete="CASCADE"), primary_key=True
    ),
    Column(
        "user_id",
        BigInteger,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    ),
)

guild_admins = Table(
    "guild_admins",
    Base.metadata,
    Column(
        "guild_id", BigInteger, ForeignKey("guilds.guild_id", ondelete="CASCADE"), primary_key=True
    ),
    Column(
        "user_id",
        BigInteger,
        ForeignKey("users.user_id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    ),
)


class Owner(Base):
    __tablename__ = "owners"

    owner_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    owner_name: Mapped[str] = mapped_column(String(100))


class UserConfig(Base):
    __tablename__ = "user_configs"

    NON_SETTINGS: ClassVar[frozenset[str]] = frozenset({"user_id"})

    user_id: Mapped[int] = _snowflake_fk("users.user_id")
    user: Mapped[User] = relationship(back_populates="config")

    @classmethod
    def has_custom_settings(cls) -> ColumnElement[bool]:
        clauses: list[ColumnElement[bool]] = []

        for column in cls.__table__.columns:
            if column.name in cls.NON_SETTINGS:
                continue

            default = column.default

            if default is None or not default.is_scalar:
                raise TypeError(f"UserConfig.{column.name} needs a scalar default= to be a setting")
            clauses.append(column.is_distinct_from(default.arg))

        return or_(*clauses) if clauses else false()


class User(Timestamps, Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    display_name: Mapped[str] = mapped_column(String(100))
    global_name: Mapped[str | None] = mapped_column(String(100))
    avatar_url: Mapped[str | None] = mapped_column(Text)

    config: Mapped[UserConfig] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True, uselist=False
    )
    favorite_tracks: Mapped[list[FavoriteTrack]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="FavoriteTrack.added_in",
    )
    favorite_playlists: Mapped[list[FavoritePlaylist]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="FavoritePlaylist.added_in",
    )
    guild_memberships: Mapped[list[Guild]] = relationship(
        secondary=guild_members, back_populates="members", passive_deletes=True
    )
    guild_adminships: Mapped[list[Guild]] = relationship(
        secondary=guild_admins, back_populates="admins", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"User({self.user_id}, {self.display_name!r})"

    @classmethod
    def is_inactive(cls) -> ColumnElement[bool]:
        return and_(
            ~cls.guild_memberships.any(),
            ~cls.guild_adminships.any(),
            ~cls.favorite_tracks.any(),
            ~cls.favorite_playlists.any(),
            ~cls.config.has(UserConfig.has_custom_settings()),
        )


class FavoriteTrack(Base):
    __tablename__ = "favorite_tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(256))
    url: Mapped[str] = mapped_column(Text)
    duration: Mapped[int] = mapped_column(BigInteger)
    uploader: Mapped[str] = mapped_column(String(256))
    added_in: Mapped[datetime] = mapped_column(server_default=func.now())

    user: Mapped[User] = relationship(back_populates="favorite_tracks")


class FavoritePlaylist(Base):
    __tablename__ = "favorite_playlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(256))
    url: Mapped[str] = mapped_column(Text)
    count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    uploader: Mapped[str] = mapped_column(String(256))
    added_in: Mapped[datetime] = mapped_column(server_default=func.now())

    user: Mapped[User] = relationship(back_populates="favorite_playlists")


class GuildAutoRoleConfig(Base):
    __tablename__ = "guild_auto_role_configs"

    guild_id: Mapped[int] = _snowflake_fk("guild_configs.guild_id")
    active: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    role_id: Mapped[int | None] = mapped_column(BigInteger)
    role_name: Mapped[str | None] = mapped_column(String(100))

    guild_config: Mapped[GuildConfig] = relationship(back_populates="auto_role_config")


class GuildWelcomeChannelConfig(Base):
    __tablename__ = "guild_welcome_channel_configs"

    guild_id: Mapped[int] = _snowflake_fk("guild_configs.guild_id")
    active: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    channel_id: Mapped[int | None] = mapped_column(BigInteger)
    channel_name: Mapped[str | None] = mapped_column(String(100))
    embed_title: Mapped[str | None] = mapped_column(String(256))
    embed_description: Mapped[str | None] = mapped_column(String(4096))
    embed_color: Mapped[int | None] = mapped_column(Integer)
    show_pfp_option: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    guild_config: Mapped[GuildConfig] = relationship(back_populates="welcome_channel_config")


class GuildConfig(Base):
    __tablename__ = "guild_configs"

    guild_id: Mapped[int] = _snowflake_fk("guilds.guild_id")
    guild: Mapped[Guild] = relationship(back_populates="config")

    auto_role_config: Mapped[GuildAutoRoleConfig] = relationship(
        back_populates="guild_config",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    welcome_channel_config: Mapped[GuildWelcomeChannelConfig] = relationship(
        back_populates="guild_config",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )

    @classmethod
    def with_defaults(cls) -> GuildConfig:
        return cls(
            auto_role_config=GuildAutoRoleConfig(),
            welcome_channel_config=GuildWelcomeChannelConfig(),
        )


class Guild(Timestamps, Base):
    __tablename__ = "guilds"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    guild_name: Mapped[str] = mapped_column(String(100))
    guild_icon_url: Mapped[str | None] = mapped_column(Text)

    config: Mapped[GuildConfig] = relationship(
        back_populates="guild", cascade="all, delete-orphan", passive_deletes=True, uselist=False
    )
    members: Mapped[list[User]] = relationship(
        secondary=guild_members, back_populates="guild_memberships", passive_deletes=True
    )
    admins: Mapped[list[User]] = relationship(
        secondary=guild_admins, back_populates="guild_adminships", passive_deletes=True
    )

    def __repr__(self) -> str:
        return f"Guild({self.guild_id}, {self.guild_name!r})"
