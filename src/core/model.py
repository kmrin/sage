from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

import crescent
import hikari

if TYPE_CHECKING:
    import miru
    import ongaku

    from core.database import Database
    from core.emojis import Emojis
    from core.sync import GuildSync
    from models.settings import Settings

__all__ = ("SageModel", "SagePlugin", "model_of")


@dataclass(slots=True, kw_only=True)
class SageModel:
    settings: Settings
    database: Database
    emojis: Emojis
    sync: GuildSync
    miru: miru.Client
    ongaku: ongaku.Client
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))


SagePlugin = crescent.Plugin[hikari.GatewayBot, SageModel]


def model_of(ctx: crescent.Context | crescent.AutocompleteContext) -> SageModel:
    return cast("SageModel", ctx.client.model)
