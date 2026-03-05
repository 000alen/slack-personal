#!/usr/bin/env python3
"""Personal Slack workspace CLI via session tokens (xoxc + xoxd). No app install required."""

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

CONFIG_DIR = Path(os.environ.get("SG_CONFIG_DIR", Path.home() / ".config" / "slack-personal"))
CREDS_PATH = CONFIG_DIR / "credentials.json"
USERS_CACHE = CONFIG_DIR / "users_cache.json"

SLACK_API = "https://slack.com/api"


# ── Credentials ───────────────────────────────────────────────────────────

def load_creds() -> dict:
    if not CREDS_PATH.exists():
        print("error: credentials not found. run: sg auth", file=sys.stderr)
        sys.exit(1)
    with open(CREDS_PATH) as f:
        return json.load(f)


def get_headers_and_cookies(creds: dict | None = None) -> tuple[dict, dict]:
    creds = creds or load_creds()
    headers = {"Authorization": f"Bearer {creds['token']}"}
    cookies = {"d": creds["cookie"]}
    return headers, cookies


# ── HTTP Client ───────────────────────────────────────────────────────────

async def slack_get(client: httpx.AsyncClient, method: str, params: dict | None = None) -> dict:
    """Make a Slack API GET request with rate limit handling."""
    creds = load_creds()
    headers, _ = get_headers_and_cookies(creds)
    url = f"{SLACK_API}/{method}"
    cookies = {"d": creds["cookie"]}

    for attempt in range(3):
        resp = await client.get(url, params=params or {}, headers=headers, cookies=cookies)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 5))
            print(f"rate limited, waiting {retry_after}s...", file=sys.stderr)
            await asyncio.sleep(retry_after)
            continue
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            err = data.get("error", "unknown error")
            if err == "token_revoked" or err == "invalid_auth":
                print(f"error: {err} — re-run: sg auth", file=sys.stderr)
                sys.exit(1)
            print(f"slack error: {err}", file=sys.stderr)
            sys.exit(1)
        return data
    print("error: max retries exceeded", file=sys.stderr)
    sys.exit(1)


async def slack_post(client: httpx.AsyncClient, method: str, data: dict | None = None) -> dict:
    """Make a Slack API POST request with rate limit handling."""
    creds = load_creds()
    headers, _ = get_headers_and_cookies(creds)
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    url = f"{SLACK_API}/{method}"
    cookies = {"d": creds["cookie"]}

    for attempt in range(3):
        resp = await client.post(url, data=data or {}, headers=headers, cookies=cookies)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 5))
            print(f"rate limited, waiting {retry_after}s...", file=sys.stderr)
            await asyncio.sleep(retry_after)
            continue
        resp.raise_for_status()
        result = resp.json()
        if not result.get("ok"):
            err = result.get("error", "unknown error")
            if err in ("token_revoked", "invalid_auth"):
                print(f"error: {err} — re-run: sg auth", file=sys.stderr)
                sys.exit(1)
            print(f"slack error: {err}", file=sys.stderr)
            sys.exit(1)
        return result
    print("error: max retries exceeded", file=sys.stderr)
    sys.exit(1)


# ── User Resolution ──────────────────────────────────────────────────────

_user_cache: dict[str, str] = {}


async def load_users(client: httpx.AsyncClient):
    """Load and cache user ID → name mapping."""
    global _user_cache
    if _user_cache:
        return

    # Try disk cache first (< 1 day old)
    if USERS_CACHE.exists():
        mtime = USERS_CACHE.stat().st_mtime
        if time.time() - mtime < 86400:
            with open(USERS_CACHE) as f:
                _user_cache = json.load(f)
            return

    # Fetch from API
    cursor = None
    while True:
        params = {"limit": 200}
        if cursor:
            params["cursor"] = cursor
        data = await slack_get(client, "users.list", params)
        for member in data.get("members", []):
            name = member.get("real_name") or member.get("name") or member.get("id")
            _user_cache[member["id"]] = name
        cursor = data.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    # Save to disk
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(USERS_CACHE, "w") as f:
        json.dump(_user_cache, f)


def resolve_user(user_id: str) -> str:
    return _user_cache.get(user_id, user_id)


# ── Auth ──────────────────────────────────────────────────────────────────

async def cmd_auth(args):
    """Extract or manually input session tokens."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(CONFIG_DIR, 0o700)

    if args.manual:
        token = input("xoxc- token: ").strip()
        cookie = input("xoxd- cookie (d value): ").strip()
        workspace = input("workspace URL (e.g. mycompany.slack.com): ").strip()
    elif args.browser:
        print("extracting from browser...")
        print("")
        print("manual steps:")
        print("1. open Slack in your browser (app.slack.com)")
        print("2. DevTools → Application → Cookies → app.slack.com")
        print("3. copy the 'd' cookie value (starts with xoxd-)")
        print("4. DevTools → Console → paste:")
        print('   JSON.parse(localStorage.localConfig_v2).teams')
        print("5. find your workspace and copy the 'token' value (starts with xoxc-)")
        print("")
        token = input("xoxc- token: ").strip()
        cookie = input("xoxd- cookie: ").strip()
        workspace = input("workspace URL: ").strip()
    else:
        # Try auto-extraction from desktop app
        try:
            from slacktokens import get_tokens_and_cookie
            print("extracting from Slack desktop app (app must be closed)...")
            result = get_tokens_and_cookie()
            cookie = result["cookie"]["value"]

            tokens = result["tokens"]
            if len(tokens) == 1:
                ws_name = list(tokens.keys())[0]
                token = tokens[ws_name]["token"]
                workspace = tokens[ws_name]["url"]
                print(f"found workspace: {ws_name} ({workspace})")
            else:
                print("found workspaces:")
                for i, (name, info) in enumerate(tokens.items()):
                    print(f"  [{i}] {name} — {info['url']}")
                idx = int(input("select workspace number: ").strip())
                ws_name = list(tokens.keys())[idx]
                token = tokens[ws_name]["token"]
                workspace = tokens[ws_name]["url"]
        except ImportError:
            print("slacktokens not installed. use --manual or --browser instead.", file=sys.stderr)
            print("or: uv pip install slacktokens", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"auto-extraction failed: {e}", file=sys.stderr)
            print("try --manual or --browser instead", file=sys.stderr)
            sys.exit(1)

    # Validate
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {token}"}
        cookies = {"d": cookie}
        resp = await client.get(f"{SLACK_API}/auth.test", headers=headers, cookies=cookies)
        data = resp.json()
        if not data.get("ok"):
            print(f"auth failed: {data.get('error', 'unknown')}", file=sys.stderr)
            sys.exit(1)

    creds = {
        "token": token,
        "cookie": cookie,
        "workspace": workspace,
        "user_id": data.get("user_id"),
        "team": data.get("team"),
        "user": data.get("user"),
    }
    with open(CREDS_PATH, "w") as f:
        json.dump(creds, f, indent=2)
    os.chmod(CREDS_PATH, 0o600)

    print(f"authenticated as {data.get('user')} @ {data.get('team')}")


# ── Workspaces ────────────────────────────────────────────────────────────

async def cmd_workspaces(args):
    """List workspaces accessible from stored tokens."""
    try:
        from slacktokens import get_tokens_and_cookie
        result = get_tokens_and_cookie()
        for name, info in result["tokens"].items():
            print(f"{name} — {info['url']}")
    except ImportError:
        # Fallback: just show current
        creds = load_creds()
        print(f"{creds.get('team', '?')} — {creds.get('workspace', '?')}")


# ── Channels ──────────────────────────────────────────────────────────────

async def cmd_channels(args):
    """List all accessible channels."""
    async with httpx.AsyncClient() as client:
        channels = []
        cursor = None
        while True:
            params = {"types": "public_channel,private_channel,mpim,im", "limit": 200}
            if cursor:
                params["cursor"] = cursor
            data = await slack_get(client, "conversations.list", params)
            channels.extend(data.get("channels", []))
            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        # For IMs, resolve user names
        if any(c.get("is_im") for c in channels):
            await load_users(client)

        count = 0
        for ch in channels:
            if args.limit and count >= args.limit:
                break
            if ch.get("is_im"):
                name = f"DM: {resolve_user(ch.get('user', '?'))}"
                ctype = "dm"
            elif ch.get("is_mpim"):
                name = ch.get("name", "?")
                ctype = "group-dm"
            elif ch.get("is_private"):
                name = ch.get("name", "?")
                ctype = "private"
            else:
                name = ch.get("name", "?")
                ctype = "public"

            unread = ""
            if ch.get("unread_count_display"):
                unread = f" ({ch['unread_count_display']} unread)"
            print(f"[{ctype}] {name} (id:{ch['id']}){unread}")
            count += 1


# ── Read ──────────────────────────────────────────────────────────────────

async def cmd_read(args):
    """Read messages from a channel."""
    async with httpx.AsyncClient() as client:
        await load_users(client)
        params = {"channel": args.channel, "limit": args.limit}
        data = await slack_get(client, "conversations.history", params)

        messages = []
        for msg in data.get("messages", []):
            user = resolve_user(msg.get("user", "?"))
            ts = datetime.fromtimestamp(float(msg.get("ts", 0))).strftime("%Y-%m-%d %H:%M")
            text = msg.get("text", "")
            files_tag = ""
            if msg.get("files"):
                fnames = [f.get("name", "unnamed") for f in msg["files"]]
                files_tag = f" [files: {', '.join(fnames)}]"
            messages.append(f"[{ts}] {user}: {text}{files_tag}")

        for m in reversed(messages):
            print(m)


# ── Search ────────────────────────────────────────────────────────────────

async def cmd_search(args):
    """Search messages across all channels."""
    async with httpx.AsyncClient() as client:
        params = {
            "query": args.query,
            "count": min(args.limit, 100),
            "sort": args.sort or "timestamp",
            "sort_dir": "desc",
        }
        data = await slack_get(client, "search.messages", params)

        matches = data.get("messages", {}).get("matches", [])
        total = data.get("messages", {}).get("total", 0)
        print(f"found {total} results (showing {len(matches)})\n")

        for msg in matches:
            user = msg.get("username", "?")
            ch_name = msg.get("channel", {}).get("name", "?")
            ts = datetime.fromtimestamp(float(msg.get("ts", 0))).strftime("%Y-%m-%d %H:%M")
            text = (msg.get("text", "") or "")[:200]
            permalink = msg.get("permalink", "")
            print(f"[{ch_name}] [{ts}] {user}: {text}")
            if permalink:
                print(f"  └─ {permalink}")


# ── Unread ────────────────────────────────────────────────────────────────

async def cmd_unread(args):
    """Show channels with unread messages."""
    async with httpx.AsyncClient() as client:
        await load_users(client)
        channels = []
        cursor = None
        while True:
            params = {"types": "public_channel,private_channel,mpim,im", "limit": 200, "exclude_archived": "true"}
            if cursor:
                params["cursor"] = cursor
            data = await slack_get(client, "conversations.list", params)
            channels.extend(data.get("channels", []))
            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        count = 0
        for ch in channels:
            unread = ch.get("unread_count_display", 0)
            if not unread:
                continue
            if args.limit and count >= args.limit:
                break

            if ch.get("is_im"):
                name = f"DM: {resolve_user(ch.get('user', '?'))}"
            else:
                name = ch.get("name", "?")

            # Get latest message preview
            preview = ""
            try:
                hist = await slack_get(client, "conversations.history", {"channel": ch["id"], "limit": 1})
                msgs = hist.get("messages", [])
                if msgs:
                    preview = (msgs[0].get("text", "") or "")[:100]
            except Exception:
                pass

            print(f"{name}: {unread} unread")
            if preview:
                print(f"  └─ {preview}")
            count += 1


# ── Files ─────────────────────────────────────────────────────────────────

async def cmd_files(args):
    """List shared files."""
    async with httpx.AsyncClient() as client:
        params = {"count": args.limit}
        if args.channel:
            params["channel"] = args.channel
        data = await slack_get(client, "files.list", params)

        for f in data.get("files", []):
            name = f.get("name", "unnamed")
            ftype = f.get("filetype", "?")
            size = f.get("size", 0)
            created = datetime.fromtimestamp(f.get("created", 0)).strftime("%Y-%m-%d %H:%M")
            url = f.get("url_private", "")
            size_str = f"{size // 1024}KB" if size > 1024 else f"{size}B"
            print(f"[{created}] {name} ({ftype}, {size_str})")
            if url:
                print(f"  └─ {url}")


# ── Download ──────────────────────────────────────────────────────────────

async def cmd_download(args):
    """Download a file by URL."""
    creds = load_creds()
    headers, _ = get_headers_and_cookies(creds)
    cookies = {"d": creds["cookie"]}

    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(args.url, headers=headers, cookies=cookies)
        resp.raise_for_status()

        # Determine filename
        filename = args.url.split("/")[-1].split("?")[0]
        out_dir = args.output or "."
        out_path = Path(out_dir) / filename
        out_path.write_bytes(resp.content)
        print(f"saved: {out_path} ({len(resp.content)} bytes)")


# ── Export ────────────────────────────────────────────────────────────────

async def cmd_export(args):
    """Export channel history to markdown."""
    async with httpx.AsyncClient() as client:
        await load_users(client)

        # Get channel info
        ch_info = await slack_get(client, "conversations.info", {"channel": args.channel})
        ch = ch_info.get("channel", {})
        ch_name = ch.get("name") or resolve_user(ch.get("user", args.channel))

        # Calculate oldest timestamp
        oldest = None
        if args.since:
            val = args.since
            if val.endswith("d"):
                oldest = (datetime.now(timezone.utc) - timedelta(days=int(val[:-1]))).timestamp()
            elif val.endswith("w"):
                oldest = (datetime.now(timezone.utc) - timedelta(weeks=int(val[:-1]))).timestamp()
            elif val.endswith("h"):
                oldest = (datetime.now(timezone.utc) - timedelta(hours=int(val[:-1]))).timestamp()

        # Fetch messages (paginated)
        all_msgs = []
        cursor = None
        while len(all_msgs) < args.limit:
            params = {"channel": args.channel, "limit": min(200, args.limit - len(all_msgs))}
            if oldest:
                params["oldest"] = str(oldest)
            if cursor:
                params["cursor"] = cursor
            data = await slack_get(client, "conversations.history", params)
            msgs = data.get("messages", [])
            if not msgs:
                break
            all_msgs.extend(msgs)
            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        # Format
        lines = []
        for msg in reversed(all_msgs):
            user = resolve_user(msg.get("user", "?"))
            ts = datetime.fromtimestamp(float(msg.get("ts", 0))).strftime("%Y-%m-%d %H:%M")
            text = msg.get("text", "")
            files_tag = ""
            if msg.get("files"):
                fnames = [f.get("name", "unnamed") for f in msg["files"]]
                files_tag = f" *[files: {', '.join(fnames)}]*"
            lines.append(f"**[{ts}] {user}:** {text}{files_tag}")

        output = f"# {ch_name}\n\nExported: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n---\n\n"
        output += "\n\n".join(lines)

        if args.output:
            Path(args.output).write_text(output)
            print(f"exported {len(all_msgs)} messages to {args.output}")
        else:
            print(output)


# ── Info ──────────────────────────────────────────────────────────────────

async def cmd_info(args):
    """Get info about a channel or current user."""
    async with httpx.AsyncClient() as client:
        if args.channel:
            data = await slack_get(client, "conversations.info", {"channel": args.channel})
            ch = data.get("channel", {})
            print(f"Name: {ch.get('name', '?')}")
            print(f"ID: {ch.get('id', '?')}")
            print(f"Topic: {ch.get('topic', {}).get('value', '-')}")
            print(f"Purpose: {ch.get('purpose', {}).get('value', '-')}")
            print(f"Members: {ch.get('num_members', '?')}")
            print(f"Private: {ch.get('is_private', False)}")
            print(f"Created: {datetime.fromtimestamp(ch.get('created', 0)).strftime('%Y-%m-%d')}")
        else:
            data = await slack_get(client, "auth.test")
            print(f"User: {data.get('user', '?')}")
            print(f"User ID: {data.get('user_id', '?')}")
            print(f"Team: {data.get('team', '?')}")
            print(f"Team ID: {data.get('team_id', '?')}")
            print(f"URL: {data.get('url', '?')}")


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(prog="sg", description="Personal Slack CLI (session tokens)")
    sub = parser.add_subparsers(dest="command", required=True)

    # auth
    p = sub.add_parser("auth", help="Extract or input session tokens")
    p.add_argument("--manual", action="store_true", help="Manually paste tokens")
    p.add_argument("--browser", action="store_true", help="Guide for browser extraction")

    # workspaces
    sub.add_parser("workspaces", help="List accessible workspaces")

    # channels
    p = sub.add_parser("channels", help="List all channels")
    p.add_argument("--limit", type=int, default=50)

    # read
    p = sub.add_parser("read", help="Read messages from a channel")
    p.add_argument("channel", help="Channel ID")
    p.add_argument("--limit", type=int, default=20)

    # search
    p = sub.add_parser("search", help="Search messages across workspace")
    p.add_argument("query", help="Search query")
    p.add_argument("--sort", choices=["score", "timestamp"], default="timestamp")
    p.add_argument("--limit", type=int, default=20)

    # unread
    p = sub.add_parser("unread", help="Show unread channels")
    p.add_argument("--limit", type=int, default=30)

    # files
    p = sub.add_parser("files", help="List shared files")
    p.add_argument("--channel", help="Filter by channel ID")
    p.add_argument("--limit", type=int, default=20)

    # download
    p = sub.add_parser("download", help="Download a file")
    p.add_argument("url", help="File URL (url_private from files list)")
    p.add_argument("--output", "-o", help="Output directory")

    # export
    p = sub.add_parser("export", help="Export channel to markdown")
    p.add_argument("channel", help="Channel ID")
    p.add_argument("--since", help="Time window: 7d, 2w, 24h")
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--output", "-o", help="Output file path")

    # info
    p = sub.add_parser("info", help="Channel or self info")
    p.add_argument("channel", nargs="?", help="Channel ID (omit for self)")

    args = parser.parse_args()
    cmd_map = {
        "auth": cmd_auth,
        "workspaces": cmd_workspaces,
        "channels": cmd_channels,
        "read": cmd_read,
        "search": cmd_search,
        "unread": cmd_unread,
        "files": cmd_files,
        "download": cmd_download,
        "export": cmd_export,
        "info": cmd_info,
    }
    asyncio.run(cmd_map[args.command](args))


if __name__ == "__main__":
    main()
