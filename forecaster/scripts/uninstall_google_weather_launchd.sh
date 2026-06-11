#!/usr/bin/env bash
set -euo pipefail

LABEL="com.jaxson.sfo-weather-google-refresh"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
echo "uninstalled $LABEL"
