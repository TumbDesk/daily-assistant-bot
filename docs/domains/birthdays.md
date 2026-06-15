# Birthdays

Users can store birthdays and see them in the daily agenda and optional morning reports.

## Key components

| File | Responsibility |
|------|----------------|
| `services/agenda.py` | Birthday queries, age calculation, agenda assembly |
| `handlers/agenda_handler.py` | `/birthday` / `/geburtstag`, `/birthdays` / `/geburtstage` |
| `handlers/birthday_handler.py` | Birthday list UI |
| `handlers/birthday_edit_handler.py` | Edit/delete birthday conversations |
| `handlers/birthday_ui.py` | Inline keyboard helpers |

## Model

`Birthday` (`database/models.py`):

- `user_id` — owner
- `name` — person's name
- `birth_date` — date of birth (year used for age)

Unique constraint on `(user_id, name, birth_date)`.

## Commands

| Command | Description |
|---------|-------------|
| `/birthday` / `/geburtstag <name> <DD.MM.YYYY>` | Add a birthday |
| `/birthdays` / `/geburtstage` | List upcoming birthdays with inline management |

Date format is parsed via `CalendarService.parse_date()`.

## Agenda integration

`AgendaService` in `services/agenda.py`:

- Computes **age** for birthdays occurring today
- Handles leap-year edge cases (`_birthday_occurrence_on`)
- `days_until_next_birthday()` for list sorting

Today's birthdays appear in:

- `/agenda` output
- Scheduled daily reports (if `include_birthdays` is enabled in `/settings`)

## Editing

Inline list → detail view → edit name/date or delete. Implemented via `birthday_edit_handler.py` with `/cancel` fallback.
