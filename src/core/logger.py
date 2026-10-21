from __future__ import annotations

import functools
import logging
import sys
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Final

from rich.console import Console
from rich.text import Text
from rich.traceback import Traceback

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path
    from types import TracebackType

    from core.paths import Paths

__all__ = (
    "DATE_FORMAT",
    "LogSession",
    "Logger",
    "get_logger",
    "rotate_latest_log",
    "set_debug",
    "setup_logging",
)

DATE_FORMAT: Final = "%d.%m.%y-%H:%M"
HISTORY_STAMP: Final = "%Y-%m-%d_%H-%M-%S"
LINE_FORMAT: Final = "[%(asctime)s] %(name)s %(levelname)s: %(message)s"

logging.addLevelName(logging.WARNING, "WARN")
logging.addLevelName(logging.CRITICAL, "FATAL")

LEVEL_STYLES: Final[Mapping[int, str]] = {
    logging.DEBUG: "dim",
    logging.INFO: "",
    logging.WARNING: "yellow",
    logging.ERROR: "red",
    logging.CRITICAL: "bold red",
}

QUIET_LOGGERS: Final[Mapping[str, int]] = {
    "sqlalchemy.engine": logging.WARNING,
    "sqlalchemy.pool": logging.WARNING,
    "hikari.ratelimits": logging.WARNING,
    "asyncio": logging.WARNING,
    "alembic.runtime.plugins": logging.WARNING,
    "alembic.ddl.postgresql": logging.WARNING,
}

type ExcInfo = bool | BaseException

_setup_lock = threading.Lock()
_handlers: list[logging.Handler] = []


class LineFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__(fmt=LINE_FORMAT, datefmt=DATE_FORMAT)

    def format_line(self, record: logging.LogRecord) -> str:
        return (
            f"[{self.formatTime(record, DATE_FORMAT)}] "
            f"{record.name} {record.levelname}: {record.getMessage()}"
        )


class RichConsoleHandler(logging.Handler):
    def __init__(self, console: Console | None = None) -> None:
        super().__init__()

        self.console = console or Console(file=sys.stdout, soft_wrap=True, highlight=False)
        self.line_formatter = LineFormatter()
        self.setFormatter(self.line_formatter)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            style = LEVEL_STYLES.get(record.levelno, "")
            self.console.print(Text(self.line_formatter.format_line(record), style=style))
            exc_info = record.exc_info
            if exc_info and exc_info[0] is not None and exc_info[1] is not None:
                self.console.print(
                    Traceback.from_exception(
                        exc_info[0], exc_info[1], exc_info[2], show_locals=False
                    )
                )
        except Exception:
            self.handleError(record)


class Logger:
    __slots__ = ("_logger", "name")

    def __init__(self, name: str) -> None:
        self.name = name
        self._logger = logging.getLogger(name)

    def __repr__(self) -> str:
        return f"Logger({self.name!r})"

    def debug(self, message: object, *args: object) -> None:
        self._log(logging.DEBUG, message, args)

    def info(self, message: object, *args: object) -> None:
        self._log(logging.INFO, message, args)

    def warn(self, message: object, *args: object) -> None:
        self._log(logging.WARNING, message, args)

    warning = warn

    def error(self, message: object, *args: object, exc_info: ExcInfo = False) -> None:
        self._log(logging.ERROR, message, args, exc_info=exc_info)

    def exception(self, message: object, *args: object) -> None:
        self._log(logging.ERROR, message, args, exc_info=True)

    def critical(self, message: object, *args: object, exc_info: ExcInfo = False) -> None:
        self._log(logging.CRITICAL, message, args, exc_info=exc_info)

    def is_debug(self) -> bool:
        return self._logger.isEnabledFor(logging.DEBUG)

    def _log(
        self, level: int, message: object, args: tuple[object, ...], *, exc_info: ExcInfo = False
    ) -> None:
        if self._logger.isEnabledFor(level):
            self._logger.log(level, message, *args, exc_info=exc_info, stacklevel=3)


@functools.cache
def get_logger(name: str) -> Logger:
    return Logger(name)


@dataclass(frozen=True, slots=True)
class LogSession:
    boot_time: datetime
    log_file: Path | None
    rotated_to: Path | None


def setup_logging(
    paths: Paths | None = None,
    *,
    debug: bool = False,
    to_file: bool = True,
    console: Console | None = None,
) -> LogSession:
    boot_time = datetime.now().astimezone()
    rotated_to: Path | None = None
    log_file: Path | None = None

    with _setup_lock:
        root = logging.getLogger()

        for handler in _handlers:
            root.removeHandler(handler)
            handler.close()

        _handlers.clear()
        _handlers.append(RichConsoleHandler(console))

        if to_file:
            if paths is None:
                raise ValueError("setup_logging(to_file=True) needs a Paths instance")
            rotated_to = rotate_latest_log(paths)
            paths.boot_marker.write_text(boot_time.isoformat(), encoding="utf-8")
            file_handler = logging.FileHandler(paths.latest_log, mode="a", encoding="utf-8")
            file_handler.setFormatter(LineFormatter())
            _handlers.append(file_handler)
            log_file = paths.latest_log

        for handler in _handlers:
            root.addHandler(handler)

        for name, level in QUIET_LOGGERS.items():
            logging.getLogger(name).setLevel(level)

        logging.captureWarnings(True)
        set_debug(debug)
        sys.excepthook = _log_uncaught

    return LogSession(boot_time=boot_time, log_file=log_file, rotated_to=rotated_to)


def set_debug(enabled: bool) -> None:
    logging.getLogger().setLevel(logging.DEBUG if enabled else logging.INFO)


def rotate_latest_log(paths: Paths) -> Path | None:
    latest = paths.latest_log

    if not latest.is_file():
        return None

    if latest.stat().st_size == 0:
        latest.unlink()
        return None

    created = _read_boot_marker(paths) or datetime.fromtimestamp(latest.stat().st_mtime)
    stem = created.strftime(HISTORY_STAMP)
    target = paths.log_history / f"{stem}-sage.log"
    counter = 1

    while target.exists():
        target = paths.log_history / f"{stem}.{counter}-sage.log"
        counter += 1

    paths.log_history.mkdir(parents=True, exist_ok=True)
    latest.replace(target)
    paths.boot_marker.unlink(missing_ok=True)

    return target


def _read_boot_marker(paths: Paths) -> datetime | None:
    try:
        return datetime.fromisoformat(paths.boot_marker.read_text(encoding="utf-8").strip())
    except OSError, ValueError:
        return None


def _log_uncaught(
    exc_type: type[BaseException], exc: BaseException, traceback: TracebackType | None
) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, traceback)
        return
    logging.getLogger("Sage").critical("Uncaught exception", exc_info=(exc_type, exc, traceback))
