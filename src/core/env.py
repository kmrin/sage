from __future__ import annotations

from pathlib import Path
from typing import Final

from dotenv import load_dotenv

__all__ = ("ENV_FILE", "load_env")

ENV_FILE: Final = Path(__file__).resolve().parents[2] / ".env"


def load_env() -> bool:
    if not ENV_FILE.is_file():
        return False
    return load_dotenv(ENV_FILE, override=False)
