# Travel

Travel trips let the daily agenda show weather at a vacation destination during a date range.

## Key components

| File | Responsibility |
|------|----------------|
| `services/travel.py` | Trip CRUD, active trip resolution |
| `handlers/travel_handler.py` | `/trip` / `/reise`, `/trips` / `/reisen` |
| `handlers/travel_edit_handler.py` | Edit/delete trip conversations |
| `handlers/travel_ui.py` | Inline list UI |

## Model

`TravelTrip` (`database/models.py`):

- `destination` — display name
- `latitude`, `longitude` — from geocoding at creation time
- `start_date`, `end_date` — inclusive trip range
- `user_id` — owner

Indexed by `(user_id, start_date, end_date)` for active-trip queries.

## Commands

| Command | Description |
|---------|-------------|
| `/trip` / `/reise` | Wizard: destination (geocoded) + start/end dates |
| `/trips` / `/reisen` | List trips with inline edit/delete |

Validation: `end_date` must not be before `start_date` (`LocalizedError: err_trip_end_before_start`).

## Active trip

`TravelService.get_active_trip(user_id, on_date)` returns a trip where `on_date` falls between `start_date` and `end_date`.

Used by agenda/report builders to fetch destination weather via `services/weather.py`.

## Agenda display

When a trip is active today, the agenda includes a "Travel weather" section with forecast for the stored coordinates and destination name.

## Editing

Inline list from `/trips` / `/reisen` → detail → edit destination or dates, or delete. Conversations support `/cancel`.
