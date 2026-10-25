from __future__ import annotations

import importlib.util
import pkgutil
from typing import TYPE_CHECKING, Any

from core.logger import get_logger
from core.paths import paths

if TYPE_CHECKING:
    import crescent

__all__ = (
    "category_event_modules",
    "command_modules",
    "event_modules",
    "load_plugins",
    "plugin_modules",
)

log = get_logger("Loader")

COMMAND_MODULE = "commands"
CATEGORY_EVENT_MODULE = "events"


def _categories() -> list[str]:
    found: list[str] = []
    for info in sorted(pkgutil.iter_modules([str(paths.package / "commands")]), key=_name):
        if not info.ispkg or info.name.startswith("_"):
            continue
        if importlib.util.find_spec(f"commands.{info.name}.{COMMAND_MODULE}") is None:
            log.warn("Command category %r has no %s.py, skipping", info.name, COMMAND_MODULE)
            continue
        found.append(info.name)
    return found


def command_modules() -> list[str]:
    """`commands.<cat>.commands` for every category package"""
    return [f"commands.{category}.{COMMAND_MODULE}" for category in _categories()]


def category_event_modules() -> list[str]:
    """`commands.<cat>.events` for every category that has one"""
    return [module for category in _categories() if (module := _category_events(category))]


def _category_events(category: str) -> str | None:
    module = f"commands.{category}.{CATEGORY_EVENT_MODULE}"
    return module if importlib.util.find_spec(module) is not None else None


def event_modules() -> list[str]:
    return [
        f"events.{info.name}"
        for info in sorted(pkgutil.iter_modules([str(paths.package / "events")]), key=_name)
        if not info.ispkg and not info.name.startswith("_")
    ]


def plugin_modules() -> list[str]:
    modules: list[str] = []
    for category in _categories():
        modules.append(f"commands.{category}.{COMMAND_MODULE}")
        if events := _category_events(category):
            modules.append(events)
    return [*modules, *event_modules()]


def load_plugins(client: crescent.Client) -> int:
    modules = plugin_modules()
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
