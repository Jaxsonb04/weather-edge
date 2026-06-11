#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 scripts/weatheredge_health_check.py "$@"
bash scripts/run_semgrep.sh
bash scripts/run_tests.sh
python3 -m compileall forecaster trading/sfo_kalshi_quant trading/tests scripts
