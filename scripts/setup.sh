#!/bin/bash
# One-time setup for slack-personal
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== slack-personal setup ==="

# 1. Check uv
if ! command -v uv &>/dev/null; then
    echo "installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# 2. Install deps
echo "syncing dependencies..."
cd "$REPO_DIR"
uv sync

# 3. Auth
echo ""
echo "choose auth method:"
echo "  [1] Auto-extract from Slack desktop app (macOS/Linux, app must be closed)"
echo "  [2] Browser extraction (guided steps)"
echo "  [3] Manual paste (you have xoxc + xoxd ready)"
echo ""
read -rp "choice [1/2/3]: " choice

case "$choice" in
    1) uv run sg auth ;;
    2) uv run sg auth --browser ;;
    3) uv run sg auth --manual ;;
    *) echo "invalid choice"; exit 1 ;;
esac

echo ""
echo "=== setup complete ==="
echo "usage: uv run sg <command>"
