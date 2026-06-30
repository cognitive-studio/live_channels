#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

AGENT="${1:-}"
CHANNEL="${2:-}"

if [[ -z "$AGENT" || -z "$CHANNEL" ]]; then
  cat <<'EOF'
Usage:
  bash scripts/bootstrap.sh <agent> <channel>

Examples:
  bash scripts/bootstrap.sh Wibey terminal-a
  bash scripts/bootstrap.sh Prudence terminal-b
  bash scripts/bootstrap.sh Atlas atlas-window
EOF
  exit 2
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is required" >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git is required" >&2
  exit 1
fi

mkdir -p messages .live_channels
chmod +x scripts/live_channels.py scripts/live_channels_ops.py scripts/bootstrap.sh || true

python3 scripts/live_channels.py init --agent "$AGENT" --channel "$CHANNEL"
python3 scripts/live_channels_ops.py doctor

cat <<EOF

Live Channels initialized.

Agent:   $AGENT
Channel: $CHANNEL

Open messages:
EOF
python3 scripts/live_channels.py inbox --agent "$AGENT" --channel "$CHANNEL" || true

cat <<EOF

Start watching:
  python3 scripts/live_channels.py watch --agent "$AGENT" --channel "$CHANNEL" --pull

Show the shared board:
  python3 scripts/live_channels_ops.py board --pull
EOF
