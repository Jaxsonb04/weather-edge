#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.jaxson.sfo-weather-google-refresh"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs/sfo-weather-forecaster"

mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"
touch "$LOG_DIR/google_weather_refresh.log" "$LOG_DIR/google_weather_refresh.err.log"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>WorkingDirectory</key>
  <string>$ROOT_DIR</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$ROOT_DIR/scripts/refresh_google_weather.sh</string>
  </array>
  <key>StartCalendarInterval</key>
  <array>
EOF

for hour in 5 6 7 8 9 10 11 12 13 14 15 16 17 18; do
  for minute in 10 40; do
    cat >> "$PLIST" <<EOF
    <dict><key>Hour</key><integer>$hour</integer><key>Minute</key><integer>$minute</integer></dict>
EOF
  done
done

cat >> "$PLIST" <<EOF
  </array>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/google_weather_refresh.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/google_weather_refresh.err.log</string>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "installed $LABEL"
echo "schedule: every 30 minutes from 05:10 through 18:40 local time"
echo "logs: $LOG_DIR/google_weather_refresh.log"
