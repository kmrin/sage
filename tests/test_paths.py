from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.paths import DEFAULT_HOME, PathError, Paths


def test_defaults_point_at_var_lib_sage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SAGE_HOME", raising=False)
    paths = Paths()
    home = DEFAULT_HOME.absolute()
    assert paths.home == home
    assert paths.temp == home / "temp"
    assert paths.logs == home / "logs"
    assert paths.log_history == home / "logs" / "history"
    assert paths.latest_log == home / "logs" / "latest.log"


def test_home_comes_from_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SAGE_HOME", str(tmp_path))
    assert Paths().home == tmp_path


def test_package_is_src() -> None:
    paths = Paths()
    assert paths.package.name == "src"
    assert (paths.package / "main.py").is_file()
    assert paths.locales == paths.package / "locales"


def test_ensure_creates_missing_dirs(tmp_path: Path) -> None:
    paths = Paths(home=tmp_path / "new" / "sage")
    created = paths.ensure()
    assert set(created) == set(paths.writable_dirs)
    assert all(directory.is_dir() for directory in paths.writable_dirs)
    assert paths.ensure() == []  # idempotent


def test_ensure_reports_a_file_in_the_way(tmp_path: Path) -> None:
    home = tmp_path / "sage"
    home.mkdir()
    (home / "logs").write_text("not a directory")
    with pytest.raises(PathError, match="not a directory"):
        Paths(home=home).ensure()


@pytest.mark.skipif(getattr(os, "geteuid", lambda: 0)() == 0, reason="root ignores permissions")
def test_ensure_reports_unwritable_dirs(tmp_path: Path) -> None:
    home = tmp_path / "sage"
    paths = Paths(home=home)
    paths.ensure()
    paths.temp.chmod(0o500)
    try:
        with pytest.raises(PathError, match="not writable"):
            paths.ensure()
    finally:
        paths.temp.chmod(0o700)


def test_asset_rejects_traversal(tmp_paths: Paths) -> None:
    assert tmp_paths.asset("images", "logo.png") == (tmp_paths.assets / "images/logo.png").resolve()
    with pytest.raises(PathError):
        tmp_paths.asset("..", "main.py")
