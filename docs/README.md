# Documentation

Daily Assistant Bot is a layered Telegram application:

```
Telegram → handlers/ → services/ → database/
                ↓
            views/ + locales/
```

## Architecture

| Layer | Role | Key paths |
|-------|------|-----------|
| **Handlers** | Parse Telegram updates (commands, callbacks, conversations) | `handlers/` |
| **Services** | Business logic, parsing, scheduling, external APIs | `services/` |
| **Database** | Persistence (SQLAlchemy models, SQLite by default) | `database/` |
| **Views** | User-facing text and inline keyboards | `views/message_factory.py`, `views/keyboards.py` |
| **Locales** | Translatable strings | `locales/en.json`, `locales/de.json` |

On startup (`main.py`):

1. Environment variables are validated (`BOT_TOKEN`, `ADMIN_ID`).
2. The database is initialized (`database.init_db`).
3. All handlers are registered (`handlers.register_all_handlers`).
4. After the bot connects, `post_init` restores scheduler jobs and bootstraps group chat metadata.

## Domain documentation

| Domain | Description |
|--------|-------------|
| [Events](domains/events.md) | Calendar events, recurrence, exceptions, reminders |
| [Categories & flags](domains/categories-and-flags.md) | Global and personal categories, event flags |
| [Birthdays](domains/birthdays.md) | Birthday storage and agenda integration |
| [Weather](domains/weather.md) | Open-Meteo integration, forecasts, alerts |
| [Travel](domains/travel.md) | Trip entries for vacation weather |
| [Agenda & reports](domains/agenda-and-reports.md) | Daily agenda and scheduled reports |
| [Auth & users](domains/auth-and-users.md) | Whitelist, admin, group membership |
| [i18n](domains/i18n.md) | Locale resolution and translation files |

## Command reference

All bot commands are listed in [commands.md](commands.md). Each command has short English and German aliases where applicable.

## Data model (overview)

Core entities in `database/models.py`:

- **User** — global profile (home location, report settings, locale)
- **UserIdentity** — links Telegram ID to a User
- **Event** — appointment with optional recurrence and group context
- **EventException** — skip or reschedule a single occurrence
- **Category**, **Flag** — event organization
- **Birthday** — name and birth date per user
- **TravelTrip** — destination and date range
- **BotChat**, **UserChatMembership** — group chat tracking

## Versioning

The bot version is defined in `version.py` (`__version__`) and exposed via the admin `/version` command.
