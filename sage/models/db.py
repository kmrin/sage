from sqlalchemy import (
    ForeignKey,
    String,
    Integer,
    Boolean,
    DateTime,
    CheckConstraint,
    UniqueConstraint,
    Table,
    Column,
    select,
    event,
    func,
    and_,
)

from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    validates,
)

from ..log import loggers

logger = loggers.DB


class Base(DeclarativeBase):
    pass


guild_members = Table(
    "guild_members",
    Base.metadata,
    Column("guild_id", Integer, ForeignKey("guilds.guild_id"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.user_id"), primary_key=True)
)

guild_admins = Table(
    "guild_admins",
    Base.metadata,
    Column("guild_id", Integer, ForeignKey("guilds.guild_id"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.user_id"), primary_key=True)
)

guild_blacklist = Table(
    "guild_blacklist",
    Base.metadata,
    Column("guild_id", Integer, ForeignKey("guilds.guild_id"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.user_id"), primary_key=True)
)


class Owner(Base):
    __tablename__ = "owners"
    
    owner_id: Mapped[int] = mapped_column(primary_key=True)
    owner_name: Mapped[str] = mapped_column(String(100))


class UserConfig(Base):
    __tablename__ = "user_config"
    
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    user: Mapped["User"] = relationship(back_populates="config")
    
    translate_private: Mapped[bool] = mapped_column(Boolean(), default=False, nullable=False)
    fact_check_private: Mapped[bool] = mapped_column(Boolean(), default=False, nullable=False)

    @validates("translate_private", "fact_check_private")
    def normalize_bools(self, key, value) -> bool:
        if value is None or value == 0:
            return False
        if value == 1:
            return True
        return bool(value)


class FavouriteTrack(Base):
    __tablename__ = "favourite_tracks"
    __table_args__ = (
        UniqueConstraint("user_id", "url", name="uq_favourite_track_user_url"),
    )
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), index=True)
    user: Mapped["User"] = relationship(back_populates="favourite_tracks")

    title: Mapped[str] = mapped_column(String(200), nullable=True)
    url: Mapped[str] = mapped_column(String(255), index=True)
    duration: Mapped[str] = mapped_column(String(20), nullable=True)
    uploader: Mapped[str] = mapped_column(String(100), nullable=True)
    added_in: Mapped[DateTime] = mapped_column(
        DateTime(), server_default=func.now(), nullable=False
    )


class FavouritePlaylist(Base):
    __tablename__ = "favourite_playlists"
    __table_args__ = (
        UniqueConstraint("user_id", "url", name="uq_favourite_playlist_user_url"),
    )
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), index=True)
    user: Mapped["User"] = relationship(back_populates="favourite_playlists")

    title: Mapped[str] = mapped_column(String(200), nullable=True)
    url: Mapped[str] = mapped_column(String(255), index=True)
    count: Mapped[int] = mapped_column(
        Integer,
        CheckConstraint("count >= 1"),
        nullable=False,
        default=1
    )
    uploader: Mapped[str] = mapped_column(String(100), nullable=True)
    added_in: Mapped[DateTime] = mapped_column(
        DateTime(), server_default=func.now(), nullable=False
    )


class User(Base):
    __tablename__ = "users"
    
    config: Mapped["UserConfig"] = relationship(
        "UserConfig", cascade="all, delete-orphan", uselist=False, back_populates="user"
    )
    favourite_tracks: Mapped[list["FavouriteTrack"]] = relationship(
        "FavouriteTrack", back_populates="user", cascade="all, delete-orphan"
    )
    favourite_playlists: Mapped[list["FavouritePlaylist"]] = relationship(
        "FavouritePlaylist", back_populates="user", cascade="all, delete-orphan"
    )
    
    guild_memberships: Mapped[list["Guild"]] = relationship(
        "Guild", secondary=guild_members, back_populates="members"
    )
    guild_adminships: Mapped[list["Guild"]] = relationship(
        "Guild", secondary=guild_admins, back_populates="admins"
    )
    guild_blacklists: Mapped[list["Guild"]] = relationship(
        "Guild", secondary=guild_blacklist, back_populates="blacklist"
    )
    
    user_id: Mapped[int] = mapped_column(primary_key=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), index=True)
    global_name: Mapped[str] = mapped_column(String(255), index=True, nullable=True)
    avatar_url: Mapped[str] = mapped_column(String(255), nullable=True)


class GuildConfig(Base):
    __tablename__ = "guild_config"
    
    guild_id: Mapped[int] = mapped_column(ForeignKey("guilds.guild_id"), primary_key=True)
    guild: Mapped["Guild"] = relationship(back_populates="config")
    
    auto_role_active: Mapped[bool] = mapped_column(Boolean(), default=False, nullable=False)
    auto_role_id: Mapped[int] = mapped_column(nullable=True, index=True)
    auto_role_name: Mapped[str] = mapped_column(String(255), nullable=True)
    
    welcome_active: Mapped[bool] = mapped_column(Boolean(), default=False, nullable=False)
    welcome_channel_id: Mapped[int] = mapped_column(nullable=True, index=True)
    welcome_channel_name: Mapped[str] = mapped_column(String(255), nullable=True)
    welcome_embed_title: Mapped[str] = mapped_column(String(255), nullable=True)
    welcome_embed_description: Mapped[str] = mapped_column(String(255), nullable=True)
    welcome_embed_colour: Mapped[str] = mapped_column(String(7), nullable=True, default="#FFFFFF")
    welcome_show_pfp: Mapped[int] = mapped_column(
        Integer,
        CheckConstraint("welcome_show_pfp >= 0 AND welcome_show_pfp <= 2"),
        nullable=False,
        default=0
    )
    
    @validates("auto_role_active", "welcome_active")
    def normalize_bools(self, key, value) -> bool:
        if value is None or value == 0:
            return False
        if value == 1:
            return True
        return bool(value)


class Guild(Base):
    __tablename__ = "guilds"
    
    config: Mapped["GuildConfig"] = relationship(
        "GuildConfig", cascade="all, delete-orphan", uselist=False, back_populates="guild"
    )
    
    members: Mapped[list["User"]] = relationship(
        "User", secondary=guild_members, back_populates="guild_memberships"
    )
    admins: Mapped[list["User"]] = relationship(
        "User", secondary=guild_admins, back_populates="guild_adminships"
    )
    blacklist: Mapped[list["User"]] = relationship(
        "User", secondary=guild_blacklist, back_populates="guild_blacklists"
    )
    
    guild_id: Mapped[int] = mapped_column(primary_key=True, index=True)
    guild_name: Mapped[str] = mapped_column(String(255), index=True)
    guild_icon_url: Mapped[str] = mapped_column(String(255), nullable=True)


@event.listens_for(Session, "after_flush_postexec")
def cleanup_users(session: Session) -> None:
    logger.info("Cleaning up inactive users")
    
    inactive = session.execute(select(User.user_id).where(
        User.user_id.notin_(select(guild_members.c.user_id)),
        User.user_id.notin_(select(guild_admins.c.user_id)),
        User.user_id.notin_(select(guild_blacklist.c.user_id)),
        ~User.favourite_tracks.any(),
        ~User.favourite_playlists.any(),
        User.config.has(and_(
            UserConfig.translate_private == False,
            UserConfig.fact_check_private == False
        ))
    )).scalars().all()
    
    for user_id in inactive:
        user = session.get(User, user_id)
        if user:
            logger.info(f"Removing {user.display_name} ({user.user_id})")
            session.delete(user)