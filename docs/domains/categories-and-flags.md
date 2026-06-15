# Categories and flags

Categories organize events; flags are optional user-defined labels attached to events.

## Categories

### Model

`Category` (`database/models.py`):

- `user_id` — `NULL` for **global** categories (admin-managed), or a user UUID for **personal** categories
- `name` — unique per user (or globally unique when `user_id` is null)

### Global categories

- Set by admin via `/gcategory` / `/gkategorie <names…>`
- Names can be comma-separated; duplicates are normalized
- Available to all users when creating or editing events

### Personal categories

- Added by users via `/category` / `/kategorie <name>`
- Only visible to that user
- Same name can exist as global and personal (different scopes)

### Implementation

- `services/calendar_service.py` — `create_global_categories()`, category lookup, assignment on events
- `handlers/category_callback_handler.py` — inline category pickers during event wizards
- `handlers/admin_handler.py` — `/gcategory` / `/gkategorie`
- `handlers/user_handler.py` — `/category` / `/kategorie`

## Flags

### Model

`Flag`:

- Per-user (`user_id` required)
- `name` — unique per user
- Many-to-many with events via `event_flags` association table

### Usage

Flags are optional metadata on events, selectable during event creation/editing. They can be used for filtering or display (depending on UI context).

### Implementation

- Created implicitly when assigned to events (via calendar service)
- Managed through event wizards and field edit handlers

## UI

Category and flag selection uses inline keyboards built in `views/keyboards.py` and messages in `views/message_factory.py`. Locale keys live under `locales/*.json`.
