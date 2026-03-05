---
name: slack-personal
description: "Access a personal Slack workspace via session tokens (no app install required). Use when asked to: search Slack messages across all channels/DMs, read channel history, list channels, check unread messages, export conversations, download files, or any task requiring personal Slack access without bot tokens or workspace admin approval."
---

# slack-personal

Personal Slack workspace access via extracted session tokens (`xoxc-` + `xoxd-`). No Slack app creation or workspace admin approval needed.

## Setup

One-time: `bash scripts/setup.sh`

Three auth methods:
1. **Auto-extract** from Slack desktop app (macOS/Linux, app must be closed)
2. **Browser extraction** (guided DevTools steps)
3. **Manual paste** (if you already have tokens)

Credentials stored at `~/.config/slack-personal/credentials.json` (mode 600).

## CLI: `scripts/sg.py`

```bash
# Auth
sg auth                    # auto-extract from desktop app
sg auth --browser          # browser extraction guide
sg auth --manual           # paste tokens manually

# Browse
sg workspaces              # list accessible workspaces
sg channels [--limit N]    # list all channels with unread counts
sg info [channel-id]       # channel details or self info

# Read
sg read <channel-id> [--limit 20]      # read messages
sg search "query" [--sort timestamp]   # search across everything
sg unread [--limit 30]                 # unread summary

# Files
sg files [--channel C] [--limit 20]    # list shared files
sg download <file-url> [-o dir]        # download a file

# Export
sg export <channel-id> [--since 7d] [-o file.md]
```

## Channel identifiers

Use channel IDs (from `sg channels`). Format: `C...` (public), `G...` (private/group DM), `D...` (DM).

## Safety

- **Read-only** — no send/post/delete commands
- Session tokens = full account access. Never expose credentials.json
- Uses unsupported auth method (session tokens, not OAuth). Works but not officially blessed by Slack
- Token valid ~1 year (d cookie TTL). Re-extract when expired

## Rate limits

Built-in retry on 429. Tier 2 methods (search): 20/min. Tier 3 (history): 50/min.

## Integration with OpenClaw

```bash
cd /path/to/slack-personal && uv run sg search "keyword" --limit 10
cd /path/to/slack-personal && uv run sg unread
```
