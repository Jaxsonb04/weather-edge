#!/usr/bin/env bash
set -euo pipefail

# Pull the live paper-trading journal (decision_snapshots etc.) DOWN from the
# Lightsail box so the backtest-rescore + real-money readiness gate can run
# locally against real settled data. sync_to_lightsail.sh only pushes source
# OUT and deliberately excludes the DB, so this is the missing inbound half.
#
# Usage (from anywhere; reads the same env as sync_to_lightsail.sh):
#   export LIGHTSAIL_IP=...; export LIGHTSAIL_KEY=/path/to/key.pem
#   # or: set -a; source .local/lightsail.env; set +a
#   bash trading/deploy/aws/pull_paper_db.sh
#   PYTHONPATH=trading python3 -m sfo_kalshi_quant.cli backtest-rescore --db-path trading/data/paper_trading.db

if [[ -z "${LIGHTSAIL_IP:-}" ]]; then
  echo "Set LIGHTSAIL_IP first, e.g. export LIGHTSAIL_IP=1.2.3.4 (or source .local/lightsail.env)" >&2
  exit 1
fi
if [[ -z "${LIGHTSAIL_KEY:-}" ]]; then
  echo "Set LIGHTSAIL_KEY first, e.g. export LIGHTSAIL_KEY=\$HOME/key.pem" >&2
  exit 1
fi
if [[ ! -f "$LIGHTSAIL_KEY" ]]; then
  echo "SSH key not found: $LIGHTSAIL_KEY" >&2
  exit 1
fi

REMOTE_USER="${REMOTE_USER:-ubuntu}"
REMOTE_BASE="${REMOTE_BASE:-/opt/weatheredge}"
REMOTE_DB="${REMOTE_DB:-$REMOTE_BASE/trading/data/paper_trading.db}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEATHEREDGE_ROOT="${WEATHEREDGE_ROOT:-$(cd "$SCRIPT_DIR/../../.." && pwd)}"
LOCAL_DB="${LOCAL_DB:-$WEATHEREDGE_ROOT/trading/data/paper_trading.db}"
SSH_OPTS=(-i "$LIGHTSAIL_KEY" -o StrictHostKeyChecking=accept-new)

chmod 600 "$LIGHTSAIL_KEY"
mkdir -p "$(dirname "$LOCAL_DB")"

# Back up any existing local DB so a pull never silently clobbers local state.
if [[ -f "$LOCAL_DB" ]]; then
  backup="$LOCAL_DB.local-backup"
  cp "$LOCAL_DB" "$backup"
  echo "Backed up existing local DB -> $backup"
fi

# Checkpoint the WAL on the box so the copied file holds all committed rows, then
# pull the main DB file (the -wal/-shm are transient and not needed once merged).
ssh "${SSH_OPTS[@]}" "$REMOTE_USER@$LIGHTSAIL_IP" \
  "sqlite3 '$REMOTE_DB' 'PRAGMA wal_checkpoint(TRUNCATE);' >/dev/null 2>&1 || true"

rsync -av \
  -e "ssh -i '$LIGHTSAIL_KEY' -o StrictHostKeyChecking=accept-new" \
  "$REMOTE_USER@$LIGHTSAIL_IP:$REMOTE_DB" \
  "$LOCAL_DB"

echo "Pulled $REMOTE_USER@$LIGHTSAIL_IP:$REMOTE_DB -> $LOCAL_DB"
echo "Next: PYTHONPATH=trading python3 -m sfo_kalshi_quant.cli backtest-rescore --db-path \"$LOCAL_DB\""
