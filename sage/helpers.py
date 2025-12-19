import os
import re
import traceback

from pathlib import Path
from typing import Literal
from discord.app_commands import Choice


def get_path(path: str) -> Path:
    if path.startswith("/"):
        return Path(os.path.realpath(path))
    return Path(os.path.join(os.path.dirname(__file__), path))


def format_exception(e: Exception) -> str:
    path, line, _, _ = traceback.extract_tb(e.__traceback__)[-1]
    path = os.path.basename(path)

    return f"{type(e).__name__} [{path}:{line}] > {str(e)}"


def format_time(s: int | float) -> str:
    s = int(s) % (24 * 3600)
    h = s // 3600
    s %= 3600
    m = s // 60
    s %= 60

    if h > 0:
        return "%02dh %02dm %02ds" % (h, m, s)
    else:
        return "%02dm %02ds" % (m, s)


def split_list(l: list, chunk_size: int) -> list[list]:
    return [l[i:i + chunk_size] for i in range(0, len(l), chunk_size)]


def text_to_chunked_lines(text: str, chunk_size: int) -> list[list[str]]:
    return split_list(text.splitlines(), chunk_size)


def choice_to_bool(choice: Literal[0, 1] | Choice[int]) -> bool:
    return choice.value == 1 if isinstance(choice, Choice) else bool(choice)


def filter_dict(d: dict, keys: list[str], mode: Literal["include", "exclude"] = "exclude") -> dict:
    if mode == "include":
        return {k: v for k, v in d.items() if k in keys}
    elif mode == "exclude":
        return {k: v for k, v in d.items() if k not in keys}
    else:
        raise ValueError(f"Filter mode {mode} is invalid. Allowed modes are 'include' or 'exclude'.")


def is_valid_hex(value: str) -> bool:
    return bool(re.match(r"^[0-9a-fA-F]+$", value))