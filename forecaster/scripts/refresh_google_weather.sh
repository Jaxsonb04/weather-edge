#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_DIR="/tmp/sfo-weather-google-refresh.lock"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "refresh already running"
  exit 0
fi
trap 'rmdir "$LOCK_DIR"' EXIT

cd "$ROOT_DIR"
mkdir -p logs
touch logs/google_weather_refresh.log logs/google_weather_refresh.err.log

PYTHON_BIN="python3"
if [[ -x "$ROOT_DIR/venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/venv/bin/python"
fi

"$PYTHON_BIN" nws_ground_truth.py --days 14
"$PYTHON_BIN" google_weather_cache.py --refresh
"$PYTHON_BIN" google_weather_cache.py
"$PYTHON_BIN" build_dashboard.py
