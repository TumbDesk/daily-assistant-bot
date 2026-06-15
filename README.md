# Daily Assistant Bot

A private Telegram bot for personal scheduling: calendar events, daily agenda, birthdays, weather, and travel-aware forecasts. Built with [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot), SQLAlchemy, and SQLite.

**Note:** Commands are available in short English and German forms (e.g. `/event` or `/termin`). The bot UI supports English and German via locale files.

## Features

- **Events** — create, edit, and delete appointments; recurring series (RRULE); per-occurrence exceptions; reminders
- **Group context** — events created in Telegram groups are scoped to that chat; private chat shows a merged view
- **Categories & flags** — global categories (admin) and personal categories; optional event flags
- **Birthdays** — store birthdays with age calculation in the daily agenda
- **Daily agenda** — `/agenda` and optional scheduled morning reports (`/settings`)
- **Weather** — forecasts via [Open-Meteo](https://open-meteo.com/) (no API key); rain alerts; home location
- **Travel** — trip entries for vacation weather in the agenda
- **Access control** — whitelist model: only allowed users can use the bot
- **i18n** — German and English UI strings

## Requirements

- Python 3.12
- Telegram bot token from [BotFather](https://t.me/BotFather)
- Your Telegram user ID (e.g. from [@userinfobot](https://t.me/userinfobot))

## Quick start (local)

```bash
cp .env.example .env
# Edit .env: set BOT_TOKEN and ADMIN_ID

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

mkdir -p data
python main.py
```

## Quick start (Docker)

```bash
cp .env.example .env
# Edit .env: set BOT_TOKEN and ADMIN_ID

docker compose up -d --build
```

Data is persisted in `./data`. Locale files can be overridden via the `locales` volume in `docker-compose.yml`.

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `BOT_TOKEN` | Telegram bot token (required) | — |
| `ADMIN_ID` | Numeric Telegram user ID of the bootstrap admin (required) | — |
| `DATABASE_URL` | SQLAlchemy database URL | `sqlite:///./data/bot.db` |
| `TZ` | Timezone for scheduling and display | `Europe/Berlin` |

Placeholder values from `.env.example` are rejected at startup.

## First run

1. Set `ADMIN_ID` to your Telegram user ID before starting the bot.
2. Message the bot in a **private chat** with `/start`.
3. Add other users with `/allow <Telegram-ID> <Name>` (admin only).
4. Optional: set a home location with `/home <city>` for weather features.

The bot is designed for a **closed user group**, not public multi-tenant use.

## Tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

## Documentation

See the [docs/](docs/) folder for architecture and domain documentation:

- [Architecture overview](docs/README.md)
- [Command reference](docs/commands.md)
- Domain guides under [docs/domains/](docs/domains/)

## External services

- **Open-Meteo** — geocoding and weather forecasts (free, no API key)
- **Telegram Bot API** — via python-telegram-bot

## Project structure

```
main.py              # Entry point, env validation, handler registration
handlers/            # Telegram commands, conversations, callbacks
services/            # Domain logic (calendar, weather, agenda, auth, …)
database/            # SQLAlchemy models and session management
views/               # Message text and inline keyboards
locales/             # i18n strings (de, en)
tests/               # pytest suite
```

## License

Licensed under the MIT License. See [LICENSE](LICENSE).
