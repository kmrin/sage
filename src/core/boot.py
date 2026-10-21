from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import hikari

from core.logger import get_logger
from models.snapshots import OwnerSnapshot

if TYPE_CHECKING:
    from models.settings import DiscordSettings

__all__ = ("BootError", "BootReport", "verify_discord")

log = get_logger("Boot")


class BootError(RuntimeError):
    """A check failed in a way that makes starting pointless."""


@dataclass(frozen=True, slots=True)
class BootReport:
    bot_id: int
    bot_name: str
    owner: OwnerSnapshot


async def verify_discord(settings: DiscordSettings) -> BootReport:
    rest_app = hikari.RESTApp()
    await rest_app.start()

    try:
        async with rest_app.acquire(
            settings.token.get_secret_value(), hikari.TokenType.BOT
        ) as rest:
            try:
                me = await rest.fetch_my_user()
            except hikari.UnauthorizedError:
                raise BootError("DISCORD_TOKEN was rejected by Discord.") from None

            log.info("Token is valid for %s (%s)", me.username, me.id)

            try:
                owner = await rest.fetch_user(settings.owner_id)
            except hikari.NotFoundError:
                raise BootError(
                    f"DISCORD_OWNER_ID {settings.owner_id} is not a Discord user"
                ) from None

            if owner.is_bot:
                raise BootError(f"DISCORD_OWNER_ID {settings.owner_id} belongs to a bot")

            log.info("Owner is %s (%s)", owner.username, owner.id)

            application = await rest.fetch_application()
            _check_application(application, settings)

    except hikari.HTTPError as error:
        raise BootError(f"Discord API check failed: {error}") from error

    finally:
        await rest_app.close()

    return BootReport(bot_id=me.id, bot_name=me.username, owner=OwnerSnapshot.from_user(owner))


def _check_application(application: hikari.Application, settings: DiscordSettings) -> None:
    flags = application.flags
    requirements: list[tuple[str, hikari.ApplicationFlags]] = [
        (
            "Server Members Intent",
            hikari.ApplicationFlags.GUILD_MEMBERS_INTENT
            | hikari.ApplicationFlags.VERIFIED_FOR_GUILD_MEMBERS_INTENT,
        ),
    ]

    if settings.message_content_intent:
        requirements.append(
            (
                "Message Content Intent",
                hikari.ApplicationFlags.MESSAGE_CONTENT_INTENT
                | hikari.ApplicationFlags.MESSAGE_CONTENT_INTENT_LIMITED,
            )
        )

    missing = [name for name, accepted in requirements if not flags & accepted]

    if missing:
        raise BootError(
            f"Enable {' and '.join(missing)} in the developer portal or Discord will close the "
            "gatewey connection"
        )

    log.info("Privileged intents are enabled: %s", ", ".join(name for name, _ in requirements))

    team_members = application.team.members if application.team else {}

    if settings.owner_id != application.owner.id and settings.owner_id not in team_members:
        log.warn("DISCORD_OWNER_ID %s doesn't own this application", settings.owner_id)
