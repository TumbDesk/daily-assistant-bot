# Weather

Weather forecasts use [Open-Meteo](https://open-meteo.com/) — no API key required.

## Key components

| File | Responsibility |
|------|----------------|
| `services/weather.py` | Geocoding, forecast API, rain detection, formatting |
| `handlers/weather_handler.py` | `/weather` / `/wetter` command and inline view callbacks |
| `services/user_service.py` | `set_home_location()` persistence on User |

## External APIs

| Endpoint | Purpose |
|----------|---------|
| `geocoding-api.open-meteo.com/v1/search` | Resolve city name → coordinates |
| `api.open-meteo.com/v1/forecast` | Temperature, precipitation, WMO weather codes |

Requests use `httpx` with a 10-second timeout.

## Home location

- Set via `/home <location>` or the weather flow when no home is configured
- Stored on `User`: `home_latitude`, `home_longitude`, `home_location_name`
- Required for `/weather` / `/wetter` and home weather in agenda/reports

## `/weather` / `/wetter` command

`handlers/weather_handler.py`:

1. Resolves location (home or prompted)
2. Shows today's weather by default
3. Inline buttons switch views: today, tomorrow, 5-day trend

Views are built by `MessageFactory` with emoji from WMO code mapping in `weather.WMO_EMOJI`.

## Rain alerts

`services/weather.py` detects rain blocks (probability threshold: 30%). The scheduler can send proactive rain alerts (`tests/test_weather_alerts_scheduler.py` covers behavior).

Intensity tiers use thresholds at 50% and 70% average probability.

## Agenda integration

`build_daily_report()` in `services/agenda.py` can include:

- Home weather for today
- Travel destination weather when an active trip exists

Controlled by user settings (`include_weather` in `/settings`).

## Errors

| Exception | Meaning |
|-----------|---------|
| `LocationNotFoundError` | Geocoding returned no results |
| `WeatherServiceError` | API failure or unexpected response |
| `LocalizedError` | User-facing i18n errors |

All surface localized messages via `MessageFactory` and locale keys in `locales/*.json`.
