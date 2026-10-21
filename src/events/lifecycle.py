"""
Gateway lifecycle: initial db sync and heartbeat.
"""

from __future__ import annotations

import math

import crescent
import hikari
from crescent.ext import tasks

from core import heartbeat
from core.logger import get_logger
from core.model import SagePlugin
from core.paths import paths
from core.sync import fetch_snapshots
from models.snapshots import OwnerSnapshot

plugin = SagePlugin()
log = get_logger("Lifecycle")


@plugin.include
@crescent.event
async def on_started(event: hikari.StartedEvent) -> None:
    model = plugin.model
    me = plugin.app.get_me()
    log.info("Gateway connected as %s", me.username if me else "unknown user")

    owner = await plugin.app.rest.fetch_user(model.settings.discord.owner_id)
    await model.sync.sync_owner(OwnerSnapshot.from_user(owner))

    snapshots, present = await fetch_snapshots(plugin.app.rest)
    await model.sync.full_sync(snapshots, present)


@plugin.include
@crescent.event
async def on_stopping(event: hikari.StoppingEvent) -> None:
    log.info("Gateway is shutting down")
    paths.heartbeat.unlink(missing_ok=True)


@plugin.include
@tasks.loop(seconds=heartbeat.INTERVAL)
async def write_heartbeat() -> None:
    if plugin.app.is_alive and math.isfinite(plugin.app.heartbeat_latency):
        heartbeat.beat(paths.heartbeat)
