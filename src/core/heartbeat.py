from __future__ import annotations

import time
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ("INTERVAL", "STALE_AFTER", "age", "beat")

INTERVAL: Final = 30
STALE_AFTER: Final = INTERVAL * 3


def beat(path: Path) -> None:
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(f"{time.time():.3f}\n", encoding="ascii")
    temp.replace(path)


def age(path: Path) -> float | None:
    try:
        stamp = float(path.read_text(encoding="ascii").strip())
    except OSError, ValueError:
        return None
    return max(0.0, time.time() - stamp)
