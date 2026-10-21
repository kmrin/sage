from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from core.env import load_env
from core.logger import get_logger, setup_logging
from models.db import Base
from models.settings import DatabaseSettings

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

load_env()
setup_logging(to_file=False)
log = get_logger("Migrations")

target_metadata = Base.metadata
settings = DatabaseSettings()  # pyright: ignore[reportCallIssue]


def _configure(**kwargs: object) -> None:
    context.configure(
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        render_as_batch=False,
        **kwargs,  # pyright: ignore[reportArgumentType]
    )


def run_migrations_offline() -> None:
    _configure(
        url=settings.url.render_as_string(hide_password=False),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_sync(connection: Connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(settings.url, poolclass=pool.NullPool)
    log.info("Migrating %s:%s/%s", settings.host, settings.port, settings.db)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_sync)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
