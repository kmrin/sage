import os
import inspect

from pathlib import Path

from .helpers import get_path


class Paths:
    root = get_path(".")

    config = get_path("config/sage_client.yml")
    locale = get_path("assets/locale")

    data = get_path("/var/sage/data")
    temp = get_path("/var/sage/data/temp")

    log_latest = get_path("/var/sage/logs/latest.log")
    log_history = get_path("/var/sage/logs/history")
    log_tracebacks = get_path("/var/sage/logs/tracebacks")

    def __init__(self) -> None:
        exceptions = [
            "log_latest"
        ]

        missing = list(
            str(v) for m, v in inspect.getmembers(self)
            if isinstance(v, Path)
            if m not in exceptions
            if not v.exists()
        )
        
        if missing:
            raise FileNotFoundError(
                f"Required paths are missing:\n - {'\n - '.join(missing)}"
            )
        
        unusable = list(
            str(v) for m, v in inspect.getmembers(self)
            if isinstance(v, Path)
            if m not in exceptions
            if not os.access(v, os.R_OK | os.W_OK)
        )
        
        if unusable:
            raise PermissionError(
                f"OS denied access to required files or paths:\n - {'\n - '.join(unusable)}"
            )


paths = Paths()