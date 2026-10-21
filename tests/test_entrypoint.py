"""Runs the real entrypoint.sh with stand-in ``alembic`` and ``python`` executables."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

ENTRYPOINT = Path(__file__).parents[1] / "src" / "scripts" / "entrypoint.sh"

pytestmark = pytest.mark.skipif(sys.platform == "win32" or not shutil.which("sh"), reason="POSIX sh")

FAKE_BOT = """#!/bin/sh
# Stand-in for `python -m main`: records the signal it gets, exits like Sage would.
trap 'echo "got TERM" >> "$MARKER"; sleep 0.2; exit 0' TERM
echo "started $*" >> "$MARKER"
while :; do sleep 0.05; done
"""


def _setup(tmp_path: Path, *, alembic_status: int = 0, bot: str = FAKE_BOT) -> tuple[dict[str, str], Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (tmp_path / "app" / "src").mkdir(parents=True)
    marker = tmp_path / "marker"
    (bin_dir / "alembic").write_text(f'#!/bin/sh\necho "alembic $*" >> "$MARKER"\nexit {alembic_status}\n')
    (bin_dir / "python").write_text(bot)
    for exe in bin_dir.iterdir():
        exe.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "APP_ROOT": str(tmp_path / "app"), "MARKER": str(marker)}
    return env, marker


def _wait_for(marker: Path, text: str, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if marker.exists() and text in marker.read_text():
            return
        time.sleep(0.02)
    raise AssertionError(f"{text!r} never appeared in {marker.read_text() if marker.exists() else '<missing>'}")


@pytest.mark.parametrize(("sig", "seen"), [(signal.SIGTERM, "got TERM"), (signal.SIGINT, "got TERM")])
def test_signal_is_forwarded_and_child_status_returned(tmp_path: Path, sig: signal.Signals, seen: str) -> None:
    env, marker = _setup(tmp_path)
    process = subprocess.Popen(["sh", str(ENTRYPOINT)], env=env, stdout=subprocess.PIPE, text=True)
    _wait_for(marker, "started -m main")
    process.send_signal(sig)
    output, _ = process.communicate(timeout=10)

    lines = marker.read_text().splitlines()
    assert lines[0].startswith("alembic -c ") and lines[0].endswith("upgrade head")
    assert seen in lines
    assert process.returncode == 0
    assert f"Received SIG{sig.name[3:]}, forwarding to pid" in output
    assert "as SIGTERM" in output
    assert "Sage exited cleanly" in output


def test_bot_exit_status_is_propagated(tmp_path: Path) -> None:
    env, _ = _setup(tmp_path, bot="#!/bin/sh\nexit 78\n")
    result = subprocess.run(["sh", str(ENTRYPOINT)], env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 78
    assert "Sage exited with status 78" in result.stdout


def test_failed_migration_stops_boot(tmp_path: Path) -> None:
    env, marker = _setup(tmp_path, alembic_status=3)
    result = subprocess.run(["sh", str(ENTRYPOINT)], env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 3
    assert "started" not in marker.read_text()
    assert "Migrations failed with status 3" in result.stdout


def test_entrypoint_uses_lf_line_endings() -> None:
    assert b"\r\n" not in ENTRYPOINT.read_bytes()
