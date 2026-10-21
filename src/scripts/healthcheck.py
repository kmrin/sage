from __future__ import annotations

import sys

from core.heartbeat import STALE_AFTER, age
from core.paths import paths


def main() -> int:
    seconds = age(paths.heartbeat)
    if seconds is None:
        print(f"unhealthy: no heartbeat at {paths.heartbeat}")
        return 1
    if seconds > STALE_AFTER:
        print(f"unhealthy: last heartbeat {seconds:.0f}s ago (limit {STALE_AFTER}s)")
        return 1
    print(f"healthy: last heartbeat {seconds:.0f}s ago")
    return 0


if __name__ == "__main__":
    sys.exit(main())
