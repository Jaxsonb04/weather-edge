#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PY_MINOR="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
USER_PY_BIN="$HOME/Library/Python/$PY_MINOR/bin"
if [[ -x "$USER_PY_BIN/semgrep" ]]; then
  export PATH="$USER_PY_BIN:$PATH"
fi

if ! command -v semgrep >/dev/null 2>&1; then
  echo "Semgrep CLI not found. Install with: python3 -m pip install --user semgrep" >&2
  exit 1
fi

if python3 -c 'import certifi' >/dev/null 2>&1; then
  export SSL_CERT_FILE="${SSL_CERT_FILE:-$(python3 -c 'import certifi; print(certifi.where())')}"
fi

export SEMGREP_SEND_METRICS=off
TMP_ROOT="${TMPDIR:-/tmp}"
export SEMGREP_LOG_FILE="${SEMGREP_LOG_FILE:-$TMP_ROOT/weatheredge-semgrep.log}"
export SEMGREP_VERSION_CACHE_PATH="${SEMGREP_VERSION_CACHE_PATH:-$TMP_ROOT/weatheredge-semgrep-version}"

semgrep scan \
  --disable-version-check \
  --metrics=off \
  --config "$ROOT_DIR/.semgrep/weatheredge.yml" \
  --error \
  "$ROOT_DIR"
