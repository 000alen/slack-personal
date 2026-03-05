# slack-personal

Read-only CLI for personal Slack workspace automation via session tokens. No app install or admin approval needed.

## How it works

Extracts your `xoxc-` session token and `xoxd-` cookie from the Slack desktop app (or browser), giving you the same API access as being logged in.

## Setup

```bash
# 1. Close Slack desktop app
# 2. Run setup (installs deps via uv, extracts tokens)
bash scripts/setup.sh
```

Or manually:
```bash
uv sync
uv run sg auth --manual  # paste tokens from browser DevTools
```

## Usage

```bash
uv run sg channels         # list all channels
uv run sg read C0123ABCD   # read messages from a channel
uv run sg search "query"   # search across everything
uv run sg unread           # unread summary
uv run sg export C0123ABCD --since 7d -o chat.md  # export
```

## OpenClaw Skill

Install as a skill to give your agent access to your Slack workspace.

## ⚠️ Note

This uses session tokens, which is not officially supported by Slack. It works but is not sanctioned. Tokens are stored locally and never transmitted anywhere except to Slack's API.
