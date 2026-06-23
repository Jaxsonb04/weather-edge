"""Data-sufficiency pre-flight for the calibration-edge work (plan Phase 0.5).

Quantifies how many warm/hot examples exist on each truth source so we know
whether the calibration-edge changes are fittable/validatable BEFORE writing any
fitting code. The Kalshi-correct truth is the CLISFO daily-climate-report integer
(``clisfo_settlements`` / ``forecast_blend_daily_high.actual_high_f``); the
abundant ``weather`` observation record is a different (settlement-wrong) truth
usable only for model training and obs-truth development.

Run from the ``trading/`` directory::

    python -m sfo_kalshi_quant.data_readiness

Honors the same env vars as the engine (``SFO_KALSHI_DB``,
``SFO_FORECASTER_ROOT``) so it can be pointed at the prod databases. Read-only.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from .config import (
    COLD_COHORT,
    DEFAULT_DB_PATH,
    DEFAULT_FORECASTER_ROOT,
    HOT_COHORT,
    NORMAL_COHORT,
    WARM_COHORT,
    temperature_cohort,
)
from .forecast import ForecastDataError, SfoForecasterAdapter
from .models import target_date_from_event_ticker

# Thresholds for the readiness verdict.
MIN_TRAIN = 180  # matches run_walk_forward_calibration_backtest(min_train=180)
MIN_COHORT_FIT = 30  # min examples to fit a shrunk per-cohort correction
# (mirrors exp_tail_lstm.SHRINK_K=30: the sample size at which a per-cohort
# estimate earns roughly equal weight against the global prior).

COHORT_ORDER = (COLD_COHORT, NORMAL_COHORT, WARM_COHORT, HOT_COHORT)


def _tally(highs: Iterable[float | None]) -> dict[str, int]:
    counts = {name: 0 for name in COHORT_ORDER}
    for high in highs:
        if high is None:
            continue
        counts[temperature_cohort(float(high))] += 1
    return counts


def _fmt(counts: dict[str, int]) -> str:
    total = sum(counts.values())
    body = "  ".join(f"{name}={counts[name]}" for name in COHORT_ORDER)
    return f"total={total}   {body}"


def _weather_db(forecaster_root: Path) -> Path:
    return forecaster_root / "weather.db"


def _clisfo_map(weather_db: Path) -> dict[str, float]:
    if not weather_db.exists():
        return {}
    with sqlite3.connect(weather_db) as conn:
        try:
            rows = conn.execute(
                "SELECT local_date, max_temperature_f FROM clisfo_settlements"
            ).fetchall()
        except sqlite3.Error:
            return {}
    return {date: float(high) for date, high in rows if high is not None}


def _date_range(conn: sqlite3.Connection, table: str, column: str) -> tuple[str, str]:
    row = conn.execute(f"SELECT min({column}), max({column}) FROM '{table}'").fetchone()
    return (row[0], row[1]) if row else ("?", "?")


def _obs_daily_high_cohorts(weather_db: Path) -> tuple[dict[str, int], tuple[str, str]]:
    """Cohorts of the observation-record daily highs (approx local day, -8h)."""

    if not weather_db.exists():
        return ({name: 0 for name in COHORT_ORDER}, ("?", "?"))
    with sqlite3.connect(weather_db) as conn:
        highs = [
            row[0]
            for row in conn.execute(
                "SELECT max(temp_f) FROM weather WHERE temp_f IS NOT NULL "
                "GROUP BY date(timestamp,'-8 hours')"
            )
        ]
        rng = _date_range(conn, "weather", "date(timestamp,'-8 hours')")
    return (_tally(highs), rng)


def _decision_coverage(
    paper_db: Path, clisfo: dict[str, float]
) -> dict[str, object]:
    if not paper_db.exists():
        return {}
    with sqlite3.connect(paper_db) as conn:
        all_days = [r[0] for r in conn.execute("SELECT DISTINCT target_date FROM decision_snapshots")]
        approved_days = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT target_date FROM decision_snapshots WHERE approved=1"
            )
        ]
    settled = [d for d in all_days if d in clisfo]
    settled_approved = [d for d in approved_days if d in clisfo]
    return {
        "decision_days": len(all_days),
        "approved_days": len(approved_days),
        "settled_days": len(settled),
        "settled_cohorts": _tally(clisfo[d] for d in settled),
        "settled_approved_days": len(settled_approved),
        "settled_approved_cohorts": _tally(clisfo[d] for d in settled_approved),
    }


def _candle_theta_cohorts(paper_db: Path, clisfo: dict[str, float]) -> dict[str, int]:
    """Event-days with Kalshi candle history joined to CLISFO truth (theta-fit sample)."""

    if not paper_db.exists():
        return {name: 0 for name in COHORT_ORDER}
    with sqlite3.connect(paper_db) as conn:
        try:
            tickers = [r[0] for r in conn.execute("SELECT DISTINCT ticker FROM dataset_kalshi_candles")]
        except sqlite3.Error:
            return {name: 0 for name in COHORT_ORDER}
    days: set[str] = set()
    for ticker in tickers:
        event = "-".join(ticker.split("-")[:2])
        try:
            days.add(target_date_from_event_ticker(event).isoformat())
        except Exception:
            continue
    return _tally(clisfo[d] for d in days if d in clisfo)


def _adapter_outcomes(forecaster_root: Path) -> dict[str, tuple[int, dict[str, int]]]:
    """Exact outcome sets the calibration backtest would consume, by truth."""

    adapter = SfoForecasterAdapter(forecaster_root)
    out: dict[str, tuple[int, dict[str, int]]] = {}
    for label, loader in (
        ("clean_blend (CLISFO truth)", adapter.load_clean_blend_outcomes),
        ("lstm (obs truth)", adapter.load_lstm_outcomes),
    ):
        try:
            outcomes = loader()
            out[label] = (len(outcomes), _tally(o.actual_high_f for o in outcomes))
        except ForecastDataError as exc:
            out[label] = (0, {"error": str(exc)})  # type: ignore[dict-item]
    return out


def _verdict(
    obs_cohorts: dict[str, int],
    *,
    lstm_clisfo_n: int,
    lstm_clisfo_cohorts: dict[str, int],
    theta_cohorts: dict[str, int],
) -> list[str]:
    lines: list[str] = []

    def mark(ok: bool) -> str:
        return "PASS" if ok else "WAIT"

    calib_ok = lstm_clisfo_n >= MIN_TRAIN
    lines.append(
        f"[{mark(calib_ok)}] CLISFO-truth calibration backtest: {lstm_clisfo_n} LSTM forecast-days "
        f"have CLISFO truth (need >= {MIN_TRAIN}). "
        + (
            "Re-score LSTM/blend forecasts against clisfo_settlements to consume it."
            if calib_ok
            else "Backfill CLISFO truth (backfill_clisfo_from_ghcn.py) to unblock."
        )
    )

    regime_obs_ok = (
        obs_cohorts.get(WARM_COHORT, 0) >= MIN_COHORT_FIT
        and obs_cohorts.get(HOT_COHORT, 0) >= MIN_COHORT_FIT
    )
    lines.append(
        f"[{mark(regime_obs_ok)}] Regime-bias FIT on obs record: "
        f"warm={obs_cohorts.get(WARM_COHORT, 0)} hot={obs_cohorts.get(HOT_COHORT, 0)} "
        f"(need >= {MIN_COHORT_FIT} each)."
    )

    regime_clisfo_ok = (
        lstm_clisfo_cohorts.get(WARM_COHORT, 0) >= MIN_COHORT_FIT
        and lstm_clisfo_cohorts.get(HOT_COHORT, 0) >= MIN_COHORT_FIT
    )
    lines.append(
        f"[{mark(regime_clisfo_ok)}] Regime-bias VALIDATION on CLISFO truth: "
        f"warm={lstm_clisfo_cohorts.get(WARM_COHORT, 0)} hot={lstm_clisfo_cohorts.get(HOT_COHORT, 0)} "
        f"(need >= {MIN_COHORT_FIT} each)."
    )

    theta_ok = (
        theta_cohorts.get(WARM_COHORT, 0) >= MIN_COHORT_FIT
        and theta_cohorts.get(HOT_COHORT, 0) >= MIN_COHORT_FIT
    )
    lines.append(
        f"[{mark(theta_ok)}] Theta market-recal FIT (Kalshi candle history ∩ CLISFO truth): "
        f"warm={theta_cohorts.get(WARM_COHORT, 0)} hot={theta_cohorts.get(HOT_COHORT, 0)} "
        f"(need >= {MIN_COHORT_FIT} each per horizon). Hot matures as summer archives (~2mo lag); hold theta=1."
    )
    return lines


def main() -> int:
    forecaster_root = DEFAULT_FORECASTER_ROOT
    paper_db = DEFAULT_DB_PATH
    weather_db = _weather_db(forecaster_root)

    print("=" * 72)
    print("DATA-READINESS PRE-FLIGHT (calibration-edge plan, Phase 0.5)")
    print(f"  forecaster_root = {forecaster_root}")
    print(f"  paper_db        = {paper_db}")
    print("=" * 72)

    clisfo = _clisfo_map(weather_db)
    print("\n# CLISFO settlements (Kalshi-correct truth) — the binding constraint")
    print("  " + _fmt(_tally(clisfo.values())) + f"   distinct_days={len(clisfo)}")

    print("\n# Backtest-visible forecast outcomes (exact sets the calibration backtest sees)")
    adapter_out = _adapter_outcomes(forecaster_root)
    for label, (n, cohorts) in adapter_out.items():
        if "error" in cohorts:
            print(f"  {label}: 0 ({cohorts['error']})")
            continue
        print(f"  {label}: n={n}   {_fmt(cohorts)}")

    print("\n# Observation record (abundant training truth; settlement-WRONG)")
    obs_cohorts, obs_rng = _obs_daily_high_cohorts(weather_db)
    print(f"  {_fmt(obs_cohorts)}   range={obs_rng[0]}..{obs_rng[1]}")

    print("\n# Trading-history coverage (theta-fit + P&L-validation sample)")
    coverage = _decision_coverage(paper_db, clisfo)
    if coverage:
        print(
            f"  decision days={coverage['decision_days']}  approved days={coverage['approved_days']}"
        )
        print(
            f"  settled (∩CLISFO) days={coverage['settled_days']}   "
            + _fmt(coverage["settled_cohorts"])  # type: ignore[arg-type]
        )
        print(
            f"  approved+settled days={coverage['settled_approved_days']}   "
            + _fmt(coverage["settled_approved_cohorts"])  # type: ignore[arg-type]
        )

    print("\n# CLISFO-truth coverage of LSTM forecast dates (calibration-backtest input post-rescore)")
    try:
        lstm_dates = {
            o.local_date.isoformat()
            for o in SfoForecasterAdapter(forecaster_root).load_lstm_outcomes()
        }
    except ForecastDataError:
        lstm_dates = set()
    lstm_clisfo = _tally(clisfo[d] for d in lstm_dates if d in clisfo)
    print(f"  pairable days={sum(lstm_clisfo.values())}   {_fmt(lstm_clisfo)}")

    print("\n# Kalshi candle history coverage (theta-fit sample, ∩ CLISFO truth)")
    theta_cohorts = _candle_theta_cohorts(paper_db, clisfo)
    print(f"  event-days={sum(theta_cohorts.values())}   {_fmt(theta_cohorts)}")

    print("\n" + "=" * 72)
    print("VERDICT")
    print("=" * 72)
    for line in _verdict(
        obs_cohorts,
        lstm_clisfo_n=sum(lstm_clisfo.values()),
        lstm_clisfo_cohorts=lstm_clisfo,
        theta_cohorts=theta_cohorts,
    ):
        print("  " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
