from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Final

__all__ = ("DEFAULT_HOME", "PathError", "Paths", "paths")

DEFAULT_HOME: Final = Path("/var/lib/sage")
HOME_ENV: Final = "SAGE_HOME"


class PathError(RuntimeError):
    """Raised when a required directory is missing, unreadable or not writable"""


class Paths:
    """
    home: Data dir. Defaults to `$SAGE_HOME` or `/var/lib/sage`.
    package: Source dir.
    """

    __slots__ = ("_home", "_package")

    def __init__(self, home: Path | None = None, package: Path | None = None) -> None:
        if home is None:
            raw = os.environ.get(HOME_ENV, "").strip()
            home = Path(raw) if raw else DEFAULT_HOME
        self._home = home.expanduser().absolute()
        self._package = (package or Path(__file__).resolve().parents[1]).absolute()

    def __repr__(self) -> str:
        return f"Paths(home={self._home}, package={self._package})"

    @property
    def home(self) -> Path:
        return self._home

    @property
    def temp(self) -> Path:
        return self._home / "temp"

    @property
    def logs(self) -> Path:
        return self._home / "logs"

    @property
    def log_history(self) -> Path:
        return self.logs / "history"

    @property
    def latest_log(self) -> Path:
        return self.logs / "latest.log"

    @property
    def boot_marker(self) -> Path:
        return self.logs / ".latest.boot"

    @property
    def heartbeat(self) -> Path:
        return self.temp / "heartbeat"

    @property
    def package(self) -> Path:
        return self._package

    @property
    def assets(self) -> Path:
        return self._package / "assets"

    @property
    def locales(self) -> Path:
        return self._package / "locales"

    @property
    def migrations(self) -> Path:
        return self._package / "migrations"

    def asset(self, *parts: str) -> Path:
        target = self.assets.joinpath(*parts).resolve()
        if not target.is_relative_to(self.assets.resolve()):
            raise PathError(f"Asset path escapes the assets directory: {'/'.join(parts)}")
        return target

    @property
    def writable_dirs(self) -> tuple[Path, ...]:
        return (self.home, self.temp, self.logs, self.log_history)

    @property
    def readable_dirs(self) -> tuple[Path, ...]:
        return (self.package, self.assets, self.locales)

    def ensure(self) -> list[Path]:
        created: list[Path] = []
        problems: list[str] = []

        for directory in self.writable_dirs:
            if not directory.exists():
                try:
                    directory.mkdir(parents=True, exist_ok=True)
                except OSError as error:
                    problems.append(f"{directory}: cannot create ({error.strerror})")
                    continue
                created.append(directory)
            if not directory.is_dir():
                problems.append(f"{directory}: exists but is not a directory")
            elif not _can_write(directory):
                problems.append(f"{directory}: not writable by {_whoami()}")

        for directory in self.readable_dirs:
            if not directory.is_dir():
                problems.append(f"{directory}: missing from the package")
            elif not os.access(directory, os.R_OK | os.X_OK):
                problems.append(f"{directory}: not readable")

        if problems:
            raise PathError("Path check failed:\n " + "\n ".join(problems))
        return created


def _whoami() -> str:
    getuid = getattr(os, "getuid", None)
    return f"uid {getuid()}" if getuid else "the current user"


def _can_write(directory: Path) -> bool:
    if not os.access(directory, os.W_OK | os.X_OK):
        return False
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".write-probe-"):
            pass
    except OSError:
        return False
    return True


paths: Final = Paths()
