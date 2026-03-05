# Slack Session Token API Notes

## Auth Model

- `xoxc-` token: per-workspace session token, stored in Slack app's LevelDB localStorage
- `xoxd-` cookie: the `d` cookie, shared across all workspaces, stored encrypted in cookie store
- Both required for every API call: `Authorization: Bearer xoxc-...` + `Cookie: d=xoxd-...`
- Token has same permissions as the logged-in user (channels, DMs, files, etc.)

## Token Extraction

### Desktop App (auto via slacktokens)
- Requires Slack app to be CLOSED (LevelDB single-reader lock)
- macOS: tokens in `~/Library/Application Support/Slack/Local Storage/leveldb/`
- Cookie decrypted from app cookie store via macOS Keychain (prompts for password)

### Browser (manual)
- DevTools → Application → Cookies → `app.slack.com` → copy `d` cookie value
- Console: `JSON.parse(localStorage.localConfig_v2).teams` → copy token from workspace entry
- Works on any OS

## Token Lifecycle
- `d` cookie TTL: ~1 year (shortened from 10 years as of Dec 2025)
- `xoxc-` token: valid while session is active
- Invalidated by: logout, password change, admin session revocation, SSO re-auth
- Re-extract when expired (takes < 1 min)

## Rate Limits (per method per workspace per token)

| Tier | Limit | Methods |
|------|-------|---------|
| 1 | 1/min | Rarely used |
| 2 | 20/min | search.messages, conversations.list, files.list |
| 3 | 50/min | conversations.history, conversations.replies |
| 4 | 100/min | users.list |
| Special | varies | chat.postMessage (1/sec/channel) |

On 429: respect `Retry-After` header.

## Known Gotchas

- xoxc tokens are NOT officially supported for API use (works but unsanctioned)
- `search.messages` is user-token only — bots cannot use it
- User IDs in messages must be resolved via `users.list` (cached locally)
- File downloads require auth headers (url_private URLs)
- Enterprise Grid: two tokens returned (workspace + org-level)
- conversations.list returns max 1000 channels per call, paginate with cursor
