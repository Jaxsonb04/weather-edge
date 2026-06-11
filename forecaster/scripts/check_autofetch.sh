#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.jaxson.sfo-weather-google-refresh"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LAUNCHD_LOG_DIR="$HOME/Library/Logs/sfo-weather-forecaster"
PROJECT_LOG_DIR="$ROOT_DIR/logs"
LAUNCHD_OUT="$LAUNCHD_LOG_DIR/google_weather_refresh.log"
LAUNCHD_ERR="$LAUNCHD_LOG_DIR/google_weather_refresh.err.log"
PROJECT_OUT="$PROJECT_LOG_DIR/google_weather_refresh.log"
PROJECT_ERR="$PROJECT_LOG_DIR/google_weather_refresh.err.log"

cd "$ROOT_DIR"

section() {
  printf '\n== %s ==\n' "$1"
}

tail_log() {
  local path="$1"
  local label="$2"
  printf '\n-- %s --\n' "$label"
  if [[ ! -e "$path" ]]; then
    printf 'missing: %s\n' "$path"
    return
  fi
  if [[ ! -s "$path" ]]; then
    printf 'empty: %s\n' "$path"
    return
  fi
  stat -f 'modified: %Sm' "$path" 2>/dev/null || true
  tail -n 25 "$path"
}

section "LaunchAgent"
PRINT_OUTPUT="$(launchctl print "gui/$(id -u)/$LABEL" 2>&1 || true)"
if [[ "$PRINT_OUTPUT" == *"Could not find service"* || "$PRINT_OUTPUT" == *"does not exist"* ]]; then
  echo "not loaded in GUI domain: $LABEL"
  printf '%s\n' "$PRINT_OUTPUT"
else
  echo "loaded in GUI domain: gui/$(id -u)/$LABEL"
  printf '%s\n' "$PRINT_OUTPUT" | awk '
    /state =|pid =|last exit code =|program =|arguments =|working directory =|standard out path =|standard error path =/ {
      gsub(/^[[:space:]]+/, "")
      print
    }
  '
fi

section "Installed Plist"
python3 - "$PLIST" <<'PY'
import plistlib
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists():
    print(f"missing: {path}")
    raise SystemExit

data = plistlib.loads(path.read_bytes())
intervals = data.get("StartCalendarInterval") or []
times = sorted(
    f"{int(row.get('Hour', 0)):02d}:{int(row.get('Minute', 0)):02d}"
    for row in intervals
)
print(f"plist: {path}")
print(f"working directory: {data.get('WorkingDirectory')}")
print(f"program: {' '.join(data.get('ProgramArguments') or [])}")
print(f"stdout: {data.get('StandardOutPath')}")
print(f"stderr: {data.get('StandardErrorPath')}")
print(f"schedule entries: {len(times)}")
if times:
    print(f"schedule window: {times[0]} through {times[-1]}")
if len(times) != 28 or (times and (times[0] != "05:10" or times[-1] != "18:40")):
    print("warning: installed schedule differs from the current 30-minute 05:10-18:40 design; rerun scripts/install_google_weather_launchd.sh")
PY

section "Google Usage"
python3 - <<'PY'
import json
from pathlib import Path

path = Path(".google_weather_usage.json")
if not path.exists():
    print("missing: .google_weather_usage.json")
    raise SystemExit

data = json.loads(path.read_text())
daily_events = data.get("daily_events", data.get("calls", data.get("refreshes")))
daily_budget = data.get("daily_event_budget", data.get("limit"))
monthly_events = data.get("monthly_events", data.get("calls", data.get("refreshes")))
monthly_budget = data.get("monthly_event_budget")
fields = [
    ("date", "date"),
    ("month", "month"),
    ("daily events", daily_events),
    ("daily budget", daily_budget),
    ("monthly events", monthly_events),
    ("monthly budget", monthly_budget),
    ("monthly free cap", "monthly_free_cap"),
    ("estimated events/refresh", "estimated_events_per_refresh"),
    ("refreshes today", "refreshes"),
    ("last refresh", "last_refresh_at"),
]
for label, key_or_value in fields:
    if isinstance(key_or_value, str):
        value = data.get(key_or_value, "n/a")
    else:
        value = key_or_value if key_or_value is not None else "n/a"
    print(f"{label}: {value}")
PY

section "Forecast Cache"
python3 - <<'PY'
import json
from datetime import datetime, timezone
from pathlib import Path

path = Path("google_weather_cache.json")
if not path.exists():
    print("missing: google_weather_cache.json")
    raise SystemExit

stat = path.stat()
age = datetime.now(timezone.utc) - datetime.fromtimestamp(stat.st_mtime, timezone.utc)
data = json.loads(path.read_text())
print(f"path: {path}")
print(f"size: {stat.st_size} bytes")
print(f"modified: {datetime.fromtimestamp(stat.st_mtime).isoformat(timespec='seconds')}")
print(f"file age: {round(age.total_seconds() / 60, 1)} minutes")
print(f"available: {data.get('available')}")
print(f"target date: {data.get('target_date')}")
print(f"fetched at: {data.get('fetched_at')}")
print(f"blend generated at: {data.get('blend_generated_at')}")
print(f"events in last Google refresh: {data.get('google_weather_events_used')}")

for row in data.get("blend_snapshots") or []:
    observed = ((row.get("details") or {}).get("observed_high_decision") or {})
    observed_text = ""
    if observed.get("mode"):
        observed_text = f", observed {observed.get('highF')}F {observed.get('mode')}"
    print(
        "blend "
        f"{row.get('target_date')}: {row.get('predicted_high_f')}F "
        f"(Google {row.get('google_high_f')}F, NWS {row.get('nws_high_f')}F, "
        f"Open-Meteo {row.get('open_meteo_high_f')}F{observed_text})"
    )
PY

section "Latest Blend Archive"
python3 - <<'PY'
import sqlite3
from pathlib import Path

db = Path("weather.db")
if not db.exists():
    print("missing: weather.db")
    raise SystemExit

with sqlite3.connect(db) as conn:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='forecast_blend_daily_high'"
    ).fetchone()
    if not exists:
        print("forecast_blend_daily_high table not found")
        raise SystemExit

    rows = conn.execute(
        """
        SELECT target_date,
               fetched_at,
               predicted_high_f,
               actual_high_f,
               abs_error_f,
               calls_used_today
        FROM forecast_blend_daily_high
        ORDER BY fetched_at DESC
        LIMIT 5
        """
    ).fetchall()

for row in rows:
    print(
        f"{row[0]} fetched {row[1]}: predicted {row[2]}F, "
        f"actual {row[3]}, abs error {row[4]}, daily events {row[5]}"
    )
PY

section "Recent Logs"
tail_log "$LAUNCHD_OUT" "launchd stdout"
tail_log "$LAUNCHD_ERR" "launchd stderr"
tail_log "$PROJECT_OUT" "manual stdout"
tail_log "$PROJECT_ERR" "manual stderr"

if [[ -e "$LAUNCHD_ERR" ]] && grep -q "Operation not permitted" "$LAUNCHD_ERR"; then
  if [[ -e "$LAUNCHD_OUT" ]] && grep -q "wrote index.html" "$LAUNCHD_OUT"; then
    printf '\nHint: launchd stderr contains old "Operation not permitted" lines, but stdout also has successful refreshes. If new runs fail, grant Full Disk Access to /bin/bash or reinstall the LaunchAgent after moving the project.\n'
  else
    printf '\nHint: launchd stderr contains "Operation not permitted". Grant Full Disk Access to /bin/bash or reinstall the LaunchAgent after moving the project.\n'
  fi
fi
