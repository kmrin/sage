from __future__ import annotations

import importlib.util
import pkgutil
from typing import TYPE_CHECKING, Any

from core.logger import get_logger
from core.paths import paths

if TYPE_CHECKING:
    import crescent

__all__ = ("command_modules", "event_modules", "load_plugins")

log = get_logger("Loader")

COMMAND_MODULE = "commands"


def command_modules() -> list[str]:
    """`commands.<cat>.commands` for every category package"""
    found: list[str] = []
    for info in sorted(pkgutil.iter_modules([str(paths.package / "commands")]), key=_name):
        if not info.ispkg or info.name.startswith("_"):
            continue
        module = f"commands.{info.name}.{COMMAND_MODULE}"
        if importlib.util.find_spec(module) is None:
            log.warn("Command category %r has no %s.py, skipping", info.name, COMMAND_MODULE)
            continue
        found.append(module)
    return found


def event_modules() -> list[str]:
    return [
        f"events.{info.name}"
        for info in sorted(pkgutil.iter_modules([str(paths.package / "events")]), key=_name)
        if not info.ispkg and not info.name.startswith("_")
    ]


def load_plugins(client: crescent.Client) -> int:
    modules = [*command_modules(), *event_modules()]
    for module in modules:
        plugin = client.plugins.load(module)
        log.info(
            "Loaded %s (%d commands, %d event listeners, %d tasks)",
            module,
            _count(plugin, "AppCommandMeta"),
            _count(plugin, "EventMeta"),
            _count(plugin, "Loop") + _count(plugin, "Cronjob"),
        )
    return len(modules)


def _name(info: pkgutil.ModuleInfo) -> str:
    return info.name


def _count(plugin: crescent.Plugin[Any, Any], kind: str) -> int:
    children = getattr(plugin, "_children", ())
    return sum(1 for child in children if type(getattr(child, "metadata", None)).__name__ == kind)
