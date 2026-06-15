# Command reference

Bot commands use **short English and German aliases** (e.g. `/event` or `/termin`). Access to most commands requires whitelist approval (`/allow`). Use `/myid` in a private chat to see your Telegram ID (works before allowlist).

## General

| Command | Access | Description |
|---------|--------|-------------|
| `/start` | Allowed users | Welcome message |
| `/help` | Allowed users | Help overview |
| `/myid` | Anyone (private chat) | Show your Telegram user ID |
| `/cancel` | Conversations | Cancel an active wizard |

## User settings

| Command | Access | Description |
|---------|--------|-------------|
| `/home <location>` | Allowed users | Set home location for weather (Open-Meteo geocoding) |
| `/category` / `/kategorie <name>` | Allowed users | Add a personal event category |
| `/settings` | Allowed users | Daily report settings (time, content toggles, locale) |

## Admin

| Command | Access | Description |
|---------|--------|-------------|
| `/allow <id> <name>` | Admin | Add a user to the whitelist |
| `/gcategory` / `/gkategorie <names…>` | Admin | Set global category names (comma-separated) |
| `/version` | Admin | Show bot version |

## Events

| Command | Access | Description |
|---------|--------|-------------|
| `/event` / `/termin` | Allowed users | Wizard or free text: create a new event |
| `/events` / `/termine` | Allowed users | List upcoming events (inline UI: open, edit, delete) |

Edit and delete are available via inline buttons on the event list and detail views — there are no public slash commands for those actions.

Events support natural-language date/time input, categories, flags, reminders, and recurrence. In group chats, events are tied to that group's context.

## Agenda & birthdays

| Command | Access | Description |
|---------|--------|-------------|
| `/agenda` | Allowed users | Today's agenda (events, birthdays, weather) |
| `/birthday` / `/geburtstag <name> <DD.MM.YYYY>` | Allowed users | Add a birthday |
| `/birthdays` / `/geburtstage` | Allowed users | List and manage birthdays (inline UI) |

## Weather

| Command | Access | Description |
|---------|--------|-------------|
| `/weather` / `/wetter` | Allowed users | Weather for home location (today / tomorrow / 5-day trend via inline buttons) |

Requires `/home` unless location is prompted in the weather flow.

## Travel

| Command | Access | Description |
|---------|--------|-------------|
| `/trip` / `/reise` | Allowed users | Add a travel trip (destination + dates) |
| `/trips` / `/reisen` | Allowed users | List and manage trips (inline UI) |

Active trips appear in the daily agenda with destination weather.

## Inline interactions

Many commands open inline keyboards for:

- Event list, detail, field edit, delete / cancel occurrence
- Birthday list and edit
- Travel trip list and edit
- Weather view switching
- Settings toggles
- Category selection during event creation

Callback routing lives in `handlers/event_callback_handler.py`, `handlers/category_callback_handler.py`, and related UI modules.
