# Events (calendar)

The event domain covers appointment CRUD, recurrence, per-occurrence exceptions, reminders, and visibility across private and group chats.

## Key components

| File | Responsibility |
|------|----------------|
| `services/calendar_service.py` | Event persistence, queries, category/flag linkage |
| `services/parser/` | Locale-aware natural-language date/time parsing (`de` / `en`) |
| `services/termin_parser.py` | Compatibility re-exports for `services.parser` |
| `services/rrule_util.py` | RRULE helpers (frequency labels, UNTIL) |
| `services/event_exceptions.py` | Skip or reschedule single occurrences |
| `services/event_filter.py` | Resolve occurrences in a date range |
| `services/occurrence_util.py` | Occurrence-level helpers |
| `services/scheduler_service.py` | Reminder job scheduling |
| `handlers/conversation_handler.py` | `/event` / `/termin` wizard |
| `handlers/termine_handler.py` | `/events` / `/termine` |
| `handlers/event_callback_handler.py` | Inline list/detail/edit/delete |
| `handlers/field_edit_handler.py` | Per-field edit conversations |

## Event model

An `Event` (`database/models.py`) stores:

- `title`, `start_datetime`, `end_datetime`, `is_all_day`
- `reminder_offset` — minutes before start (0 = none)
- `is_recurring`, `rrule` — recurrence via RRULE strings
- `category_id` — optional category
- `flags` — many-to-many via `event_flags`
- `context_chat_id` — group chat ID if created in a group; private events use the user's private chat ID
- `owner_id` — global user UUID

## Context visibility

`services/user_service.visible_context_chat_id()` defines the visibility scope:

- In a **group**, events belong to that group's chat ID (negative).
- In **private chat**, the user sees events from their private context plus groups they belong to.

`event_source_label()` adds a source suffix in lists when an event comes from another context (e.g. a group name).

## Recurrence

Supported recurrence keys map to RRULE in `calendar_service.RRULE_MAP`:

- `daily`, `weekly`, `biweekly`, `monthly`
- Optional `UNTIL` date on the RRULE

`event_filter.resolve_occurrences_in_range()` expands recurring events for display and reminders.

## Exceptions

`EventException` records:

- `exception_type` — skip (`cancel`) or reschedule (`move`)
- `original_start` — which occurrence is affected
- `new_start`, `new_end` — for moved occurrences

Handlers offer "cancel only this occurrence" vs "delete whole series" when deleting recurring events.

## Reminders

`scheduler_service` uses python-telegram-bot's job queue:

- On event create/update, schedules a one-shot reminder job
- On bot restart, `post_init` → `restore_jobs()` re-schedules pending reminders
- Reminder offsets: none, 15 minutes, 1 hour, 1 day

## Creating events

`/event` / `/termin` runs a multi-step conversation (`handlers/conversation_handler.py`):

1. Title and datetime (natural language via `services.parser`, locale from user settings)
2. Optional category, flags, reminder, recurrence
3. Confirmation

Group events automatically set `context_chat_id` from the chat where the command was issued.

## Editing and deleting

Edit and delete are available via inline buttons on `/events` / `/termine` — detail view, field edits, and delete/cancel occurrence. There are no public slash commands for these actions.

Field-level edits use dedicated sub-conversations in `field_edit_handler.py`.
