import os

from alembic import context
from sqlalchemy import pool
from sqlalchemy import engine_from_config
from logging.config import fileConfig

from sage.models.db import Base

DB_NAME = os.getenv("POSTGRES_DB", "sagedb")
DB_USER = os.getenv("POSTGRES_USER", "sageadmin")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "sageadmin")

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option(
    "sqlalchemy.url",
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@database:5432/{DB_NAME}"
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
