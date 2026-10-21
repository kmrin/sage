from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.logger import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

    from models.settings import DatabaseSettings

__all__ = ("Database", "DatabaseUnavailableError")

log = get_logger("Database")


class DatabaseUnavailableError(RuntimeError):
    """DB couldn't be reached within the configured attempts"""


class Database:
    __slots__ = ("_settings", "engine", "session")

    def __init__(self, settings: DatabaseSettings, *, echo: bool = False) -> None:
        self._settings = settings
        self.engine: AsyncEngine = create_async_engine(
            settings.url,
            echo=echo,
            pool_pre_ping=True,
            pool_size=settings.pool_size,
            max_overflow=settings.max_overflow,
            pool_recycle=1800,
        )
        self.session: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self.engine, expire_on_commit=False, autoflush=False
        )

    async def connect(self, *, attempts: int = 10, delay: float = 2.0) -> str:
        target = f"{self._settings.host}:{self._settings.port}/{self._settings.db}"

        for attempt in range(1, attempts + 1):
            try:
                async with self.engine.connect() as connection:
                    version = (await connection.execute(text("SHOW server_version"))).scalar_one()
            except (OperationalError, DBAPIError, OSError) as error:
                if attempt == attempts:
                    raise DatabaseUnavailableError(
                        f"Could not reach db at {target} after {attempts} attempts"
                    ) from error

                log.warn(
                    "DB at %s not reachable (attempt %d/%d): %s",
                    target,
                    attempt,
                    attempts,
                    _short(error),
                )

                await asyncio.sleep(delay)

            else:
                log.info("Connected to db %s at %s", version, target)
                return str(version)

        raise AssertionError("unreachable")

    async def close(self) -> None:
        await self.engine.dispose()
        log.info("Connection pool closed")


def _short(error: BaseException) -> str:
    message = str(getattr(error, "orig", None) or error)
    return message.splitlines()[0] if message else type(error).__name__
