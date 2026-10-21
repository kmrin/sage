from __future__ import annotations

import asyncio
import os
import signal
import sys

import pytest

import main
from core.paths import Paths


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT])
async def test_signals_request_a_graceful_stop(sig: signal.Signals) -> None:
    stop = asyncio.Event()
    main._install_signal_handlers(stop)
    try:
        os.kill(os.getpid(), sig)
        await asyncio.wait_for(stop.wait(), timeout=2)
    finally:
        loop = asyncio.get_running_loop()
        for handled in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(handled)
    assert stop.is_set()


def test_unusable_data_directory_exits_with_config_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("in the way")
    monkeypatch.setattr(main, "paths", Paths(home=blocker))
    monkeypatch.setattr(main, "load_env", lambda: False)
    assert main.main() == main.EXIT_CONFIG
    assert "FATAL" in capsys.readouterr().err
