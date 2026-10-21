from __future__ import annotations

import io
import re
from datetime import datetime

from rich.console import Console

from core.logger import get_logger, rotate_latest_log, setup_logging
from core.paths import Paths

LINE = re.compile(r"^\[\d{2}\.\d{2}\.\d{2}-\d{2}:\d{2}\] (?P<module>\S+) (?P<level>[A-Z]+): (?P<msg>.*)$")


def _console() -> tuple[Console, io.StringIO]:
    buffer = io.StringIO()
    return Console(file=buffer, force_terminal=True, color_system="standard", soft_wrap=True), buffer


def test_file_lines_match_the_documented_format(tmp_paths: Paths) -> None:
    console, _ = _console()
    setup_logging(tmp_paths, console=console)
    log = get_logger("Database")
    log.info("Connected")
    log.warn("Found orphan guild %s, deleting", 42)
    log.error("Query failed")

    lines = tmp_paths.latest_log.read_text(encoding="utf-8").splitlines()
    parsed = [LINE.match(line) for line in lines]
    assert all(parsed), lines
    assert [(m["module"], m["level"], m["msg"]) for m in parsed if m] == [
        ("Database", "INFO", "Connected"),
        ("Database", "WARN", "Found orphan guild 42, deleting"),
        ("Database", "ERROR", "Query failed"),
    ]
    stamp = parsed[0]["msg"] and lines[0][1:15]
    datetime.strptime(stamp, "%d.%m.%y-%H:%M")  # raises if the date format drifts


def test_console_colors(tmp_paths: Paths) -> None:
    console, buffer = _console()
    setup_logging(tmp_paths, console=console)
    log = get_logger("Colors")
    log.info("plain")
    log.warn("careful")
    log.error("broken")

    out = buffer.getvalue().splitlines()
    info, warn, error = (next(line for line in out if word in line) for word in ("plain", "careful", "broken"))
    assert "\x1b[" not in info  # default terminal color
    assert "\x1b[33m" in warn  # yellow
    assert "\x1b[31m" in error  # red


def test_exception_traceback_reaches_the_file(tmp_paths: Paths) -> None:
    console, buffer = _console()
    setup_logging(tmp_paths, console=console)
    try:
        raise ValueError("kaboom")
    except ValueError as error:
        get_logger("Tests").error("It broke", exc_info=error)
    text = tmp_paths.latest_log.read_text(encoding="utf-8")
    assert "Tests ERROR: It broke" in text
    assert "ValueError: kaboom" in text
    assert "kaboom" in buffer.getvalue()


def test_third_party_loggers_share_the_format(tmp_paths: Paths) -> None:
    import logging

    console, _ = _console()
    setup_logging(tmp_paths, console=console)
    logging.getLogger("hikari.gateway").warning("resuming")
    assert "hikari.gateway WARN: resuming" in tmp_paths.latest_log.read_text(encoding="utf-8")


def test_debug_flag_controls_level(tmp_paths: Paths) -> None:
    console, buffer = _console()
    setup_logging(tmp_paths, console=console, debug=False)
    get_logger("Tests").debug("hidden")
    setup_logging(tmp_paths, console=console, debug=True)
    get_logger("Tests").debug("shown")
    assert "hidden" not in buffer.getvalue()
    assert "shown" in buffer.getvalue()


def test_rotation_names_file_after_its_creation_time(tmp_paths: Paths) -> None:
    tmp_paths.latest_log.write_text("[old boot]\n", encoding="utf-8")
    tmp_paths.boot_marker.write_text("2026-10-19T08:15:42-03:00", encoding="utf-8")

    rotated = rotate_latest_log(tmp_paths)

    assert rotated == tmp_paths.log_history / "2026-10-19_08-15-42-sage.log"
    assert rotated.read_text(encoding="utf-8") == "[old boot]\n"
    assert not tmp_paths.latest_log.exists()


def test_setup_rotates_previous_boot_and_marks_the_new_one(tmp_paths: Paths) -> None:
    console, _ = _console()
    first = setup_logging(tmp_paths, console=console)
    get_logger("Tests").info("first boot")
    second = setup_logging(tmp_paths, console=console)

    assert first.rotated_to is None
    assert second.rotated_to is not None
    assert second.rotated_to.name == first.boot_time.strftime("%Y-%m-%d_%H-%M-%S") + "-sage.log"
    assert "first boot" in second.rotated_to.read_text(encoding="utf-8")
    assert datetime.fromisoformat(tmp_paths.boot_marker.read_text()) == second.boot_time


def test_rotation_never_overwrites_history(tmp_paths: Paths) -> None:
    for _ in range(2):
        tmp_paths.latest_log.write_text("x", encoding="utf-8")
        tmp_paths.boot_marker.write_text("2026-01-01T00:00:00+00:00", encoding="utf-8")
        rotate_latest_log(tmp_paths)
    names = sorted(p.name for p in tmp_paths.log_history.iterdir())
    assert names == ["2026-01-01_00-00-00-sage.log", "2026-01-01_00-00-00.1-sage.log"]


def test_empty_latest_log_is_discarded(tmp_paths: Paths) -> None:
    tmp_paths.latest_log.touch()
    assert rotate_latest_log(tmp_paths) is None
    assert list(tmp_paths.log_history.iterdir()) == []
