# Auth and users

Access is whitelist-based: only registered users (plus the bootstrap admin) can use bot commands.

## Key components

| File | Responsibility |
|------|----------------|
| `services/auth_service.py` | `restricted` decorator, admin checks, bootstrap |
| `services/user_service.py` | User/identity CRUD, whitelist logic |
| `services/chat_membership_service.py` | Group membership and chat titles |
| `handlers/admin_handler.py` | `/allow`, group join protection |
| `main.py` | `ADMIN_ID` env validation |

## Environment

| Variable | Role |
|----------|------|
| `ADMIN_ID` | Telegram user ID of the bootstrap admin; always allowed |
| `BOT_TOKEN` | Telegram API token |

`ADMIN_ID` must be a positive integer. Placeholder values from `.env.example` are rejected.

## Whitelist model

`UserService.is_allowed()`:

1. Bootstrap admin (`ADMIN_ID`) is always allowed.
2. If the database has **no users**, everyone is denied (except admin).
3. Otherwise, user must have a `UserIdentity` row linking their Telegram ID to a `User`.

New users are added by admin: `/allow <Telegram-ID> <Name>`.

`/myid` works **without** whitelist so users can discover their ID before being allowed.

## User identity

Global users use internal UUIDs (`User.id`). Telegram IDs map through `UserIdentity`:

- `platform` — `"telegram"`
- `platform_user_id` — string Telegram user ID

The `restricted` decorator resolves `global_user_id` into `context.user_data` for downstream handlers.

## Admin capabilities

- `/allow` — add whitelist users
- `/gcategory` / `/gkategorie` — global categories
- `/version` — bot version
- `is_admin` flag on `User` for additional admin users (beyond bootstrap)

`ensure_bootstrap_admin()` registers the admin in the database on first interaction.

## Group chat security

`handlers/admin_handler.py` listens for `ChatMemberHandler`:

- When the bot is added to a group, verifies the adder is allowed
- If not allowed: bot leaves the group and notifies admin
- If allowed: records chat in `BotChat`, alerts admin of success

## Group membership tracking

`chat_membership_service`:

- Records when allowed users interact in groups (`record_user_seen`)
- Stores chat titles for `event_source_label` display
- `bootstrap_bot_chats_from_events()` on startup rebuilds chat metadata from existing events

## Private vs group handlers

Many commands only work in private chats (e.g. `/myid`, settings). Group usage is primarily for creating context-scoped events.
