# Agenda and reports

The agenda combines today's events, birthdays, and weather into one view. Users can schedule automatic morning reports.

## Key components

| File | Responsibility |
|------|----------------|
| `services/agenda.py` | `TodayAgenda`, `build_daily_report()`, birthday/event assembly |
| `services/user_settings.py` | Report time, content toggles, locale |
| `handlers/agenda_handler.py` | `/agenda`, `/settings`, settings callbacks |
| `services/scheduler_service.py` | Daily report job scheduling |

## Manual agenda

`/agenda` builds today's view for the current user:

1. **Birthdays today** — name and age
2. **Events today** — from all visible contexts (private + groups)
3. **Weather** — home location (and travel if active)

Event lines show time or "all day", optional source suffix for cross-context events, and markers for recurring/moved occurrences.

## Scheduled reports

Users configure reports via `/settings`:

| Setting | Field on `User` | Description |
|---------|-----------------|-------------|
| Report enabled | `report_enabled` | Toggle daily report |
| Report time | `report_time` | Local time `HH:MM` |
| Include events | `include_events` | Events section in report |
| Include birthdays | `include_birthdays` | Birthdays section |
| Include weather | `include_weather` | Weather section |
| Locale | `locale` | `de` or `en` (override Telegram language) |

`scheduler_service` schedules a recurring daily job per user. `last_report_date` prevents duplicate sends on the same day.

On bot restart, `restore_jobs()` re-registers report and reminder jobs.

## `/birthday` / `/geburtstag` shortcut

Also handled in `agenda_handler.py` — quick add without opening the full birthday list UI.

## Settings UI

`/settings` shows an overview with inline toggles (time picker, locale, content sections). Callbacks update `User` via `user_settings` service and refresh the keyboard.

## Data flow

```
User settings → scheduler job (daily)
                     ↓
              build_daily_report(user_id)
                     ↓
    events (calendar + exceptions) + birthdays + weather (+ travel)
                     ↓
              Telegram message to user's private chat
```
