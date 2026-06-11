#!/usr/bin/env bash
set -euo pipefail

TRADING_DIR="${SFO_TRADING_ROOT:-/opt/weatheredge/trading}"
FORECASTER_DIR="${SFO_FORECASTER_ROOT:-/opt/weatheredge/forecaster}"
PYTHON_BIN="${SFO_TRADING_PYTHON:-$TRADING_DIR/.venv/bin/python}"
DB_PATH="${SFO_KALSHI_DB:-$TRADING_DIR/data/paper_trading.db}"
BANKROLL="${PAPER_BANKROLL:-1000}"
PROFILES_CSV="${PAPER_RISK_PROFILES:-${PAPER_RISK_PROFILE:-balanced}}"
CALIBRATION_SOURCE="${SFO_TRADING_SIGNAL_CALIBRATION_SOURCE:-lstm}"
TARGET_DATE="${SFO_PAPER_SCAN_TARGET_DATE:-rolling}"
SIDE="${SFO_PAPER_SCAN_SIDE:-both}"
TAIL_BASKET_ENABLED="${SFO_PAPER_SCAN_TAIL_BASKET_ENABLED:-1}"
TAIL_BASKET_DISTANCE="${SFO_TAIL_BASKET_DISTANCE:-3}"
TAIL_BASKET_TAIL_STAKE="${SFO_TAIL_BASKET_TAIL_STAKE:-5}"
TAIL_BASKET_CENTER_STAKE="${SFO_TAIL_BASKET_CENTER_STAKE:-1}"
TAIL_BASKET_MAX_TAIL_PROBABILITY="${SFO_TAIL_BASKET_MAX_TAIL_PROBABILITY:-0.20}"
TAIL_BASKET_MAX_SPEND="${SFO_TAIL_BASKET_MAX_SPEND:-12}"
TAIL_BASKET_MAX_WORST_LOSS="${SFO_TAIL_BASKET_MAX_WORST_LOSS:-8}"

if [[ "$PYTHON_BIN" != */* ]]; then
  if ! PYTHON_BIN="$(command -v "$PYTHON_BIN")"; then
    echo "missing trading Python runtime: $SFO_TRADING_PYTHON" >&2
    exit 1
  fi
elif [[ ! -x "$PYTHON_BIN" ]]; then
  echo "missing trading Python runtime: $PYTHON_BIN" >&2
  exit 1
fi

cd "$TRADING_DIR"

IFS=',' read -r -a profiles <<< "$PROFILES_CSV"
profile_index=0
for raw_profile in "${profiles[@]}"; do
  profile="${raw_profile//[[:space:]]/}"
  if [[ -z "$profile" ]]; then
    continue
  fi

  skip_context=0
  if (( profile_index > 0 )); then
    skip_context=1
  fi

  if [[ "$TAIL_BASKET_ENABLED" != "0" ]]; then
    basket_args=(
      --no-color
      --forecaster-root "$FORECASTER_DIR"
      --db-path "$DB_PATH"
      --bankroll "$BANKROLL"
      --risk-profile "$profile"
      tail-basket
      --target-date "$TARGET_DATE"
      --calibration-source "$CALIBRATION_SOURCE"
      --tail-distance "$TAIL_BASKET_DISTANCE"
      --tail-stake "$TAIL_BASKET_TAIL_STAKE"
      --center-stake "$TAIL_BASKET_CENTER_STAKE"
      --max-tail-probability "$TAIL_BASKET_MAX_TAIL_PROBABILITY"
      --max-basket-spend "$TAIL_BASKET_MAX_SPEND"
      --max-worst-case-loss "$TAIL_BASKET_MAX_WORST_LOSS"
      --place-paper
    )
    if (( skip_context > 0 )); then
      basket_args+=(--skip-context-snapshots)
    fi

    echo "running tail basket profile=$profile db=$DB_PATH"
    # The experimental basket must never block the broad analyzer: a missing
    # forecast or transient Kalshi error exits non-zero and set -e would
    # otherwise abort the remaining profiles.
    if ! "$PYTHON_BIN" -m sfo_kalshi_quant.cli "${basket_args[@]}"; then
      echo "warning: tail basket failed for profile=$profile; continuing with broad scan" >&2
    else
      # Only suppress the analyzer's context snapshots when the basket
      # actually recorded them.
      skip_context=1
    fi
  fi

  args=(
    --no-color
    --forecaster-root "$FORECASTER_DIR"
    --db-path "$DB_PATH"
    --bankroll "$BANKROLL"
    --risk-profile "$profile"
    analyze
    --target-date "$TARGET_DATE"
    --side "$SIDE"
    --calibration-source "$CALIBRATION_SOURCE"
    --place-paper
  )
  # Forecast/probability/market context is identical across profiles in one
  # scan; only the first profile's first command records it.
  if (( skip_context > 0 )); then
    args+=(--skip-context-snapshots)
  fi
  profile_index=$((profile_index + 1))
  if [[ -n "${PAPER_SCAN_STAKE:-}" ]]; then
    args+=(--paper-stake "$PAPER_SCAN_STAKE")
  fi
  if [[ -n "${PAPER_SCAN_DAILY_BUDGET:-}" ]]; then
    args+=(--daily-budget "$PAPER_SCAN_DAILY_BUDGET")
  fi

  echo "running paper scan profile=$profile db=$DB_PATH"
  "$PYTHON_BIN" -m sfo_kalshi_quant.cli "${args[@]}"
done
