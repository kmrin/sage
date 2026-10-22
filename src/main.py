from __future__ import annotations

import asyncio
import contextlib
import platform
import signal
import sys
from typing import TYPE_CHECKING, Final

import crescent
import hikari
import miru
import ongaku

from core import i18n
from core.boot import BootError, BootReport, verify_discord
from core.database import Database, DatabaseUnavailableError
from core.env import load_env
from core.loader import load_plugins
from core.logger import LogSession, get_logger, set_debug, setup_logging
from core.model import SageModel
from core.paths import PathError, paths
from core.sync import GuildSync
from models.settings import Settings, SettingsError, get_settings

if TYPE_CHECKING:
    from pathlib import Path

log = get_logger("Sage")

EXIT_OK: Final = 0
EXIT_FAILURE: Final = 1
EXIT_CONFIG: Final = 78  # sysexits EX_CONFIG


def main() -> int:
    env_loaded = load_env()

    try:
        created = paths.ensure()
    except PathError as error:
        print(f"[Sage] FATAL: {error}", file=sys.stderr)
        return EXIT_CONFIG

    session = setup_logging(paths)
    _log_boot(session, created, env_loaded)

    try:
        settings = get_settings()
    except SettingsError as error:
        log.critical("Invalid configuration (compare .env with .env.example)")
        for problem in error.problems:
            log.critical("  %s", problem)
        return EXIT_CONFIG

    set_debug(settings.debug)

    if settings.debug:
        log.warn("Debug mode is on")

    try:
        return asyncio.run(run(settings))
    except KeyboardInterrupt:
        log.info("Interrupted during startup")
        return EXIT_OK


async def run(settings: Settings) -> int:
    log.info(
        "Starting sage v%s (Python %s, hikari %s, crescent %s, miru %s, ongaku %s)",
        settings.version,
        platform.python_version(),
        hikari.__version__,
        crescent.__version__,
        miru.__version__,
        ongaku.__version__,
    )

    try:
        catalog = i18n.catalog()
    except i18n.LocaleError as error:
        log.critical("%s", error)
        return EXIT_CONFIG

    default_locale = i18n.configure(settings.default_locale)

    log.info(
        "Loaded %d strings in %s (default %s)",
        len(catalog.keys),
        ", ".join(map(str, catalog.locales)),
        default_locale,
    )

    if str(default_locale) != settings.default_locale:
        log.warn(
            "SAGE_DEFAULT_LOCALE %s has no locale file, using %s",
            settings.default_locale,
            default_locale,
        )

    try:
        report = await verify_discord(settings.discord)
    except BootError as error:
        log.critical("%s", error)
        return EXIT_CONFIG

    database = Database(settings.database)

    try:
        await database.connect()
    except DatabaseUnavailableError as error:
        log.critical("%s", error)
        await database.close()
        return EXIT_FAILURE

    try:
        return await _run_bot(settings, database, report)
    finally:
        await database.close()


async def _run_bot(settings: Settings, database: Database, report: BootReport) -> int:
    bot = hikari.GatewayBot(
        settings.discord.token.get_secret_value(),
        intents=settings.discord.intents,
        logs=None,  # core.logger already owns the root logger
        banner=None,
        suppress_optimization_warning=True,
    )

    miru_client = miru.Client(bot, ignore_unknown_interactions=True)
    ongaku_client = ongaku.Client(bot, logs="DEBUG" if settings.debug else "INFO")

    ongaku_client.create_session(
        "sage-lavalink",
        ssl=settings.lavalink.ssl,
        host=settings.lavalink.host,
        port=settings.lavalink.port,
        password=settings.lavalink.password.get_secret_value(),
    )

    log.info(
        "Lavalink session configured for %s:%d", settings.lavalink.host, settings.lavalink.port
    )

    sync = GuildSync(database, owner_id=report.owner.owner_id)
    model = SageModel(
        settings=settings,
        database=database,
        emojis=report.emojis,
        sync=sync,
        miru=miru_client,
        ongaku=ongaku_client,
    )

    client = crescent.Client(bot, model, default_guild=settings.dev_guild_id)

    if settings.dev_guild_id:
        log.warn(
            "Commands will register to guild %s only (SAGE_DEV_GUILD_ID)", settings.dev_guild_id
        )

    count = load_plugins(client)
    log.info("Loaded %d plugin(s)", count)

    stop = asyncio.Event()
    _install_signal_handlers(stop)

    await bot.start()
    log.info("Sage is running")

    joined = asyncio.create_task(bot.join(), name="gateway-join")
    stopped = asyncio.create_task(stop.wait(), name="stop-signal")

    try:
        done, _ = await asyncio.wait({joined, stopped}, return_when=asyncio.FIRST_COMPLETED)

        if joined in done and (error := joined.exception()) is not None:
            log.critical("Gateway connection ended with an error", exc_info=error)
            return EXIT_FAILURE

        if joined in done:
            log.warn("Gateway connection closed unexpectedly")
            return EXIT_FAILURE

        log.info("Shutting down")
        return EXIT_OK

    finally:
        stopped.cancel()
        await sync.close()
        if bot.is_alive:
            await bot.close()
        with contextlib.suppress(asyncio.CancelledError):
            await joined
        paths.heartbeat.unlink(missing_ok=True)
        log.info("Goodbye")


def _install_signal_handlers(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()

    def request_stop(name: str) -> None:
        if stop.is_set():
            log.warn("Received %s again, already shutting down", name)
            return
        log.info("Received %s, shutting down", name)
        stop.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, request_stop, sig.name)
        except NotImplementedError:
            signal.signal(
                sig, lambda _s, _f, n=sig.name: loop.call_soon_threadsafe(request_stop, n)
            )


def _log_boot(session: LogSession, created: list[Path], env_loaded: bool) -> None:
    log.info("Boot at %s", session.boot_time.isoformat(timespec="seconds"))

    if session.rotated_to is not None:
        log.info("Previous log rotated to %s", session.rotated_to)

    for directory in created:
        log.info("Created %s", directory)

    log.info("Data directory %s is ready, logging to %s", paths.home, session.log_file)

    if env_loaded:
        log.info("Loaded environment from .env")


if __name__ == "__main__":
    sys.exit(main())
