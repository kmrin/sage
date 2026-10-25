# Sage
Sage is a general-purpose Discord bot built on hikari, crescent, miru and ongaku.

## Getting started
For a dev environment: run sage on your own machine with localhost access to the database and lavalink.

```Bash
# 1. Set _HOST variables to localhost
POSTGRES_HOST=127.0.0.1
LAVALINK_HOST=127.0.0.1

# 2. Start the database and lavalink with dev settings
docker compose -f compose.yaml -f compose.dev.yaml up -d sage-db sage-lavalink

# 3. Create the test database
docker exec sage-db createdb -U sage sage_test

# 4. Run migrations
uv run alembic upgrade head

# 5. Run the test suite
uv run ruff check
uv run basedpyright src
uv run pytest

# 6. Run Sage
uv run python src/main.py
```

For a more straightforward run, as in, the version you wish to run is final, simply use docker.

```Bash
# 1. Set _HOST variables to docker hosts
POSTGRES_HOST=sage-db
LAVALINK_HOST=sage-lavalink

# 2. Build and start the stack
docker compose up -d

# 3. Follow logs to make sure things are working
docker compose logs -f
```

## Project structure
Everything Sage runs lives under `src/`, which is also the import root (`from core.i18n import tr`, not `from src.core...`).

```
src/
├── main.py                 # Entry point: loads settings, checks Discord, connects the db, builds the clients, loads plugins
├── assets/                 # Static files shipped with the bot (read-only at runtime)
│   └── docs/               # Terms of Service and Privacy Policy
├── commands/               # Slash commands, one package per category (see "How to build plugins")
│   └── core/
│       ├── commands.py     # Core commands such as /ping
│       └── models.py       # Category-local models used my core.commands
├── core/                   # Framework code shared by every plugin
│   ├── boot.py             # Pre-flight Discord checks: token, owner, privileged intents
│   ├── database.py         # Async SQLAlchemy engine + session factory
│   ├── emojis.py           # Application emoji registry and the list of emojis the code requires
│   ├── env.py              # Loads the root .env file (never overrides real environment variables)
│   ├── heartbeat.py        # Writes/reads the heartbeat file used by the container healthcheck
│   ├── i18n.py             # Locale catalog, validation and the t()/tr()/Localized/LocaleKeys helpers
│   ├── loader.py           # Discovers and loads every command category and event module
│   ├── logger.py           # Rich console + file logging, log rotation, get_logger()
│   ├── model.py            # SageModel (shared state handed to plugins), SagePlugin, model_of()
│   ├── paths.py            # Every filesystem path Sage uses (data dir, logs, assets, locales...)
│   ├── permissions.py      # Command guards: owner_only, guild_only, guild_admin, guild_specific
│   └── sync.py             # Keeps guilds, members, admins and the owner in the db in sync with Discord
├── events/                 # Gateway event listeners and timed tasks, one plugin per file
│   ├── errors.py           # Last-resort handlers for failed commands and listeners
│   ├── guilds.py           # Schedules db resyncs on guild/member/role changes
│   └── lifecycle.py        # Initial sync on startup and the heartbeat loop
├── locales/                # One TOML file per Discord locale
├── migrations/             # Alembic environment and schema revisions
├── models/                 # Shared data models
│   ├── db.py               # SQLAlchemy tables (users, guilds, configs, favorites...)
│   ├── settings.py         # Environment configuration (pydantic-settings)
│   └── snapshots.py        # Validated snapshots of Discord data used by the sync
└── scripts/
    ├── entrypoint.sh       # Container entrypoint: runs migrations, then starts Sage and forwards signals
    └── healthcheck.py      # Container healthcheck: fails when the heartbeat file goes stale
```

Runtime data (logs, the heartbeat, temporary files) is written to the data directory, `$SAGE_HOME` (default `/var/lib/sage`).

## How to build plugins
Sage is built on [crescent](https://github.com/hikari-crescent/hikari-crescent) plugins. You never register a plugin by hand: at startup [`core/loader.py`](./src/core/loader.py) loads

- `commands/<category>/commands.py` for every package in `src/commands/`, and
- `events/<name>.py` for every module in `src/events/`,

in alphabetical order. Anything whose name starts with `_` is skipped. Each of these modules must expose a module-level `plugin = SagePlugin()`, and everything you want registered is added with `@plugin.include`.

Inside a plugin you have:

| What | How |
| --- | --- |
| The hikari bot (REST, cache, `get_me()`...) | `plugin.app` |
| Shared state: `settings`, `database`, `emojis`, `sync`, `miru`, `ongaku`, `started_at` | `plugin.model` (or `model_of(ctx)` from code that only has a context) |
| A logger | `log = get_logger("MyFeature")` from `core.logger` |

### Commands and categories
A **category** is a package in `src/commands/`. The folder name is the category name, and it's used to namespace the command's locale keys (`commands.<category>.<command>.*`). A category needs two files:

```
src/commands/utility/
├── __init__.py   # empty
└── commands.py   # the plugin, loaded automatically
```

If `commands.py` is missing, the loader logs a warning and skips the category. Every other file in the folder (models, helpers, miru views...) is just a normal module you import from `commands.py`, the loader never touches it.

An example command, under the "utility" category, with an option and a permission guard:

```python
# src/commands/utility/commands.py
from __future__ import annotations

import crescent

from commands.utility.models import DiceRoll
from core.i18n import LocaleKeys, tr
from core.model import SagePlugin
from core.permissions import guild_only

plugin = SagePlugin()
roll_keys = LocaleKeys("commands.utility.roll")


@plugin.include
@guild_only
@crescent.command(
    name=roll_keys.localized("name"),
    description=roll_keys.localized("description"),
)
class Roll:
    sides = crescent.option(
        int,
        name=roll_keys.localized("options.sides.name"),
        description=roll_keys.localized("options.sides.description"),
        default=6,
        min_value=2,
        max_value=100,
    )

    async def callback(self, ctx: crescent.Context) -> None:
        result = DiceRoll.roll(self.sides)
        await ctx.respond(tr(ctx, roll_keys("response"), value=result.value, sides=result.sides))
```

Decorator order matters: `@plugin.include` on top, permission guards in the middle, `@crescent.command` at the bottom. The guards in [`core/permissions.py`](./src/core/permissions.py) answer the user with an ephemeral, translated message and stop the command:

| Guard | Who can run the command |
| --- | --- |
| `@owner_only` | The user set in `DISCORD_OWNER_ID` |
| `@guild_only` | Anyone, but only inside a server |
| `@guild_admin` / `@guild_admin(allow_owner=False)` | Members with Administrator in the current server (and the bot owner, unless disabled) |
| `@guild_specific(123, 456)` | Anyone, but only in the listed servers |

Uncaught exceptions in a command are logged by [`events/errors.py`](./src/events/errors.py) and the user gets a generic "something went wrong" reply, so you only need to handle the errors you expect.

During development, set `SAGE_DEV_GUILD_ID` so commands register to a single server instantly instead of waiting on Discord's global command propagation.

### Models and extra files
**Category-local models** go in `commands/<category>/models.py`. Use pydantic for plain data, like `Latency` in [`commands/core/models.py`](./src/commands/core/models.py):

```python
# src/commands/utility/models.py
from __future__ import annotations

import random

from pydantic import BaseModel, ConfigDict, Field


class DiceRoll(BaseModel):
    model_config = ConfigDict(frozen=True)

    sides: int = Field(ge=2)
    value: int = Field(ge=1)

    @classmethod
    def roll(cls, sides: int) -> DiceRoll:
        return cls(sides=sides, value=random.randint(1, sides))
```

**Shared models** used by more than one category go in `src/models/`.

**Database tables** go in [`models/db.py`](./src/models/db.py). Inherit from `Base` (and `Timestamps` if you want `created_at`/`updated_at`), add the class to `__all__`, then generate and apply a migration:

```Bash
uv run alembic revision --autogenerate -m "add reminders"
# review the new file in src/migrations/versions/ before applying it
uv run alembic upgrade head
```

The Docker image runs `alembic upgrade head` on every start, so committed migrations are applied automatically in production. Use the session factory to read and write:

```python
from models.db import User

async with plugin.model.database.session.begin() as session:  # commits on exit
    user = await session.get(User, ctx.user.id)
```

Things to know about the existing tables:

- **Per-user settings** are columns on `UserConfig`, and every one of them needs a scalar `default=`. The sync uses those defaults to decide if a user has custom settings, and it deletes users who are in no shared server and have no favorites or custom settings. A column without a default raises a `TypeError`.
- **Per-server feature settings** follow the `GuildAutoRoleConfig` pattern: a table keyed by `guild_configs.guild_id`, a one-to-one relationship on `GuildConfig`, and an entry in `GuildConfig.with_defaults()` so new servers get a row. Servers that already exist won't get one, so have your migration insert rows for them.
- `guilds`, `users`, `guild_members` and `guild_admins` are owned by [`core/sync.py`](./src/core/sync.py). Read them freely, but don't write to them from plugins.

**Other files:**

- **Assets**: put static files under `src/assets/` and get their path with `paths.asset("images", "banner.png")` (from `core.paths`). It refuses paths that escape the assets folder. The container filesystem is read-only, so anything written at runtime goes in `paths.temp` (inside the data directory) instead.
- **Emojis**: upload them as application emojis in the Discord developer portal, add their names to `Emojis.REQUIRED` in [`core/emojis.py`](./src/core/emojis.py), and use them with `plugin.model.emojis["name"]` (`str()` of it gives the mention). Sage refuses to start if a required emoji is missing, so typos are caught at boot instead of in the middle of a command.
- **Helpers and views**: any other module in the category folder (for example `views.py` for miru components, using `plugin.model.miru`).
- **Typing**: if you add a new base class that pydantic or SQLAlchemy evaluates at runtime, add it to `runtime-evaluated-base-classes` in `pyproject.toml`, or ruff will try to move its imports under `TYPE_CHECKING`.

### Translations (i18n)
Every user-facing string lives in `src/locales/<locale>.toml`, where `<locale>` is a Discord locale code (`en-US`, `pt-BR`, `es-ES`...). Nested tables are flattened into dotted keys:

```toml
# src/locales/en-US.toml
[commands.utility.roll]
name = "roll"
description = "Roll a die."
response = "You rolled **{value}** on a d{sides}."

[commands.utility.roll.options.sides]
name = "sides"
description = "How many sides the die has."
```

```toml
# src/locales/pt-BR.toml
[commands.utility.roll]
name = "rolar"
description = "Rola um dado."
response = "Você tirou **{value}** em um d{sides}."

[commands.utility.roll.options.sides]
name = "lados"
description = "Quantos lados o dado tem."
```

The rules, all checked at startup (Sage won't boot if any fail, and the log lists every problem):

- `en-US` is required. It's the fallback and the reference every other file is compared against.
- Every locale must have exactly the same keys as `en-US`, no missing or extra ones, and no empty values.
- Each translation must use the same `{placeholders}` as its `en-US` version. Write `{{` and `}}` for literal braces.
- Under `commands.*`, keys ending in `name` must be valid slash names (lowercase, no spaces, 1-32 characters) and keys ending in `description` must be 1-100 characters.

Add a language by creating a new file with the same keys. It's picked up on the next start.

Using strings in code:

| Helper | Use it for |
| --- | --- |
| `Localized("commands.x.y.name")` | Command, group and option names/descriptions. Discord shows the right one to each user. It fails at import time if the key doesn't exist. |
| `LocaleKeys("commands.x.y")` | Avoids repeating a prefix: `keys("response")` gives the full key, `keys.localized("name")` gives a `Localized`, `keys.child("options")` gives a nested `LocaleKeys`. |
| `tr(ctx, key, **values)` | Replies to a command. Uses the user's locale, then the server's, then the default. |
| `t(key, locale, **values)` | Anywhere without a command context (events, tasks). Pass e.g. `guild.preferred_locale`, or `None` for the default locale. |

The default locale is set with `SAGE_DEFAULT_LOCALE` (falls back to `en-US`). Keep command strings under `commands.<category>.<command>`, error messages under `errors`, and give other features their own top-level table (for example `[events.welcome]`).

### Event handlers
Create a new module in `src/events/`. It's loaded automatically:

```python
# src/events/welcome.py
from __future__ import annotations

import crescent
import hikari

from core.i18n import t
from core.logger import get_logger
from core.model import SagePlugin

plugin = SagePlugin()
log = get_logger("Welcome")


@plugin.include
@crescent.event
async def on_member_join(event: hikari.MemberCreateEvent) -> None:
    if event.member.is_bot:
        return

    guild = event.get_guild()
    locale = guild.preferred_locale if guild else None
    log.info("%s joined %s", event.user.username, event.guild_id)
    # ...
```

- crescent picks the event from the type annotation, so import the event type normally, not under `TYPE_CHECKING` (ruff is already set up for this).
- Only the events allowed by the bot's intents arrive: everything unprivileged, plus server members, plus message content unless `DISCORD_MESSAGE_CONTENT_INTENT=false`.
- Exceptions raised in listeners are logged by `events/errors.py`.
- A listener that only exists for one command category can also go in that category's `commands.py`, since both are plugins. Use `events/` for anything not tied to a single category.

### Timed events
Repeating jobs use `crescent.ext.tasks` and are included like any other listener, in an `events/` module or a category's `commands.py`:

```python
from datetime import timedelta

from crescent.ext import tasks


@plugin.include
@tasks.loop(
    minutes=10
)  # also accepts hours=, seconds=, or a timedelta: tasks.loop(timedelta(hours=1))
async def refresh_status() -> None:
    if not plugin.app.is_alive:
        return
    ...


@plugin.include
@tasks.cronjob("0 4 * * *")  # every day at 04:00; on_startup=True also runs it once at boot
async def nightly_cleanup() -> None:
    try:
        ...
    except Exception:
        log.exception("Nightly cleanup failed")
```

- Tasks start as soon as their plugin loads, before the gateway connects. A `loop` also runs once right away, so check `plugin.app.is_alive` (as the heartbeat in [`events/lifecycle.py`](./src/events/lifecycle.py) does) before using the gateway or cache.
- Cron expressions use the process's local time. In Docker that's the `TZ` variable (UTC by default).
- Errors raised in tasks are **not** caught by `events/errors.py`. Wrap the body in `try`/`except` and log failures, or the error is reported as an unhandled asyncio task exception.
- To change a loop's interval at runtime, use `refresh_status.metadata.set_interval(minutes=5)`.

After loading, the log shows what each plugin registered, e.g. `Loaded commands.utility.commands (1 commands, 0 event listeners, 0 tasks)`. It's a quick way to check your new code was picked up.

## License
This project is licensed under the **GNU Affero General Public License v3.0 (AGPLv3)**.

- You are free to use, modify, and distribute this software.
- If you modify this bot and make it availablke to others (for example, hosting a public instance) you **must** provide access to the complete corresponding source code of your modified version under the same AGPLv3 license.
- There is **no warranty** for this software; use it at your own risk.

See the [`LICENSE`](./LICENSE) file for the full license details.

## Legal documents
[Terms of Service](./src/assets/docs/terms-of-service.md) |
[Privacy Policy](./src/assets/docs/privacy-policy.md)
