from __future__ import annotations

import time

import pytest

from core import heartbeat
from core.paths import Paths
from scripts import healthcheck


@pytest.fixture
def paths(tmp_paths: Paths, monkeypatch: pytest.MonkeyPatch) -> Paths:
    monkeypatch.setattr(healthcheck, "paths", tmp_paths)
    return tmp_paths


def test_missing_heartbeat_is_unhealthy(paths: Paths) -> None:
    assert healthcheck.main() == 1


def test_fresh_heartbeat_is_healthy(paths: Paths) -> None:
    heartbeat.beat(paths.heartbeat)
    assert healthcheck.main() == 0


def test_stale_heartbeat_is_unhealthy(paths: Paths) -> None:
    paths.heartbeat.write_text(f"{time.time() - heartbeat.STALE_AFTER - 5}\n")
    assert healthcheck.main() == 1


def test_garbage_heartbeat_is_unhealthy(paths: Paths) -> None:
    paths.heartbeat.write_text("not a number")
    assert healthcheck.main() == 1
