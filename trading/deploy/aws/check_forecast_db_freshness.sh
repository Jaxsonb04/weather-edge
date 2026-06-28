#!/usr/bin/env bash
# Forecast freshness watchdog (AWS box).
#
# Once the box owns the forecaster refresh, a wedged pipeline (OOM, network blip,
# a swallowed error) leaves weather.db frozen. The trader keeps serving that stale
# high until max_forecast_age_hours (12 h live / 30 h research) silently HALTS
# trading -- and nobody is watching the Mac logs anymore. This watchdog surfaces
# staleness EARLY: it logs loudly to journald, writes a marker file, optionally
# POSTs to a webhook, and exits non-zero so `systemctl --failed` flags it.
#
# Wire a real push alert by setting SFO_FRESHNESS_ALERT_URL in /etc/weatheredge.env
# to an ntfy.sh topic, Slack/Discord incoming webhook, etc.
set -uo pipefail

FORECASTER_DIR="${SFO_FORECASTER_ROOT:-/opt/weatheredge/forecaster}"
DB="${SFO_FORECAST_DB:-$FORECASTER_DIR/weather.db}"
MAX_AGE_HOURS="${SFO_FORECAST_MAX_AGE_HOURS:-6}"
MARKER="${SFO_FORECAST_STALE_MARKER:-$FORECASTER_DIR/STALE_FORECAST}"
ALERT_URL="${SFO_FRESHNESS_ALERT_URL:-}"

now=$(date +%s)

if [[ ! -f "$DB" ]]; then
  stale=1
  age_h="n/a"
  msg="forecast DB missing: $DB"
else
  mtime=$(stat -c %Y "$DB" 2>/dev/null || stat -f %m "$DB")
  age_s=$(( now - mtime ))
  age_h=$(awk "BEGIN{printf \"%.1f\", $age_s/3600}")
  max_s=$(awk "BEGIN{printf \"%d\", $MAX_AGE_HOURS*3600}")
  if (( age_s > max_s )); then
    stale=1
    msg="forecast DB stale: $DB is ${age_h}h old (threshold ${MAX_AGE_HOURS}h)"
  else
    stale=0
  fi
fi

if (( stale == 1 )); then
  echo "STALE: $msg" >&2
  {
    date -u +%Y-%m-%dT%H:%M:%SZ
    echo "$msg"
  } > "$MARKER" 2>/dev/null || true
  if [[ -n "$ALERT_URL" ]]; then
    if curl -fsS -m 15 -X POST -H "Content-Type: text/plain" \
        --data "WeatherEdge ALERT: $msg" "$ALERT_URL" >/dev/null 2>&1; then
      echo "alert posted to SFO_FRESHNESS_ALERT_URL"
    else
      echo "alert POST failed (check SFO_FRESHNESS_ALERT_URL)" >&2
    fi
  fi
  exit 1
fi

rm -f "$MARKER" 2>/dev/null || true
echo "OK: forecast DB fresh (${age_h}h old, threshold ${MAX_AGE_HOURS}h)"
exit 0
