"""Phase 1 validation: synoptic-regime vs predicted-temp-cohort residual de-bias.

The production blend de-bias (``google_weather_cache.rolling_blend_residual_bias``
/ ``forecast_backtest.make_debias_predictor``) cohorts rolling residual
corrections by the PREDICTED temperature bin. Du & DiMego (NOAA/NCEP, 2008) show
forecast bias is *regime*-dependent: a model can be warm-biased under high pressure
but cold-biased under low pressure at the SAME temperature, so the temperature bin
is the wrong axis. This harness tests whether keying the rolling de-bias on a
leakage-safe PRIOR-DAY synoptic regime (offshore-flow) lowers warm-cohort error.

Why the LSTM, not the blend: the blend archive is only ~17 days and the ``weather``
obs table ends 2026-05-22, so the blend-side ``forecast_backtest`` cannot yet
validate this. The 442-day LSTM predictions (``ab_test_results.json``), re-scored
against the backfilled CLISFO settlement truth, are the only forecast series deep
enough. Pure stdlib: the de-bias is a post-hoc correction on already-computed
predictions, so no torch/pandas training stack is needed.

Discipline (mirrors forecast_backtest):
* Rolling-origin: corrections are learned only from days strictly before the
  scored day (history appended after the prediction).
* CLISFO truth only: predictions scored against the integer CLISFO settlement.
* No leakage in the regime label: the regime is the PRIOR calendar day's mean
  offshore-flow, fully known when the next-day forecast is committed; regime cut
  points are FIXED constants, not data-derived quantiles.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections import namedtuple
from pathlib import Path

from forecast_backtest import _cohort_corrections
from google_weather_cache import (
    ROLLING_BIAS_CAP_F,
    cap_magnitude,
    predicted_temperature_cohort,
)
from settlement_calendar import integer_settlement_high_f

DB_PATH = Path("weather.db")
AB_TEST_PATH = Path("ab_test_results.json")
SHRINK_K = 30.0  # plan Phase 1: shrink each regime's correction toward the global mean
CAP_F = ROLLING_BIAS_CAP_F
MIN_HISTORY = 30
COHORTS = ("cold", "normal", "warm", "hot")

# Fixed (leakage-free) offshore-flow regime cut points. offshore_flow = cos(wind_dir
# - 70deg): +1 = warm offshore/easterly, -1 = cool onshore sea breeze. Cuts at the
# rough p33/p75 of the realized distribution (med -0.51) -> three balanced regimes.
OFFSHORE_WARM_CUT = -0.30
OFFSHORE_COOL_CUT = -0.60

Day = namedtuple("Day", "date pred actual regime")


def settled_cohort(high: float) -> str:
    if high < 60.0:
        return "cold"
    if high < 70.0:
        return "normal"
    if high < 80.0:
        return "warm"
    return "hot"


def offshore_regime(off_flow: float | None) -> str:
    if off_flow is None:
        return "unknown"
    if off_flow > OFFSHORE_WARM_CUT:
        return "offshore"  # warm/easterly lean
    if off_flow > OFFSHORE_COOL_CUT:
        return "transitional"
    return "onshore"  # cool sea breeze


def _prior_day_offshore(conn: sqlite3.Connection) -> dict[str, float]:
    """Mean offshore-flow per local day (used as the PRIOR-day regime signal)."""

    rows = conn.execute(
        """
        SELECT date(timestamp, '-8 hours') AS d,
               avg(cos((wind_dir - 70.0) * 3.14159265358979 / 180.0)) AS off_flow
        FROM weather
        WHERE wind_dir IS NOT NULL
        GROUP BY date(timestamp, '-8 hours')
        """
    ).fetchall()
    return {d: off for d, off in rows if off is not None}


def _clisfo_truth(conn: sqlite3.Connection) -> dict[str, float]:
    truth: dict[str, float] = {}
    for d, t in conn.execute(
        "SELECT local_date, max_temperature_f FROM clisfo_settlements WHERE max_temperature_f IS NOT NULL"
    ):
        truth[d] = float(t)
    return truth


def load_days(db_path: Path, ab_test_path: Path) -> list[Day]:
    daily = json.loads(ab_test_path.read_text())["target_daily_high_next_day"]["chart"]["daily"]
    conn = sqlite3.connect(db_path)
    try:
        off_by_day = _prior_day_offshore(conn)
        truth = _clisfo_truth(conn)
    finally:
        conn.close()
    days: list[Day] = []
    for row in sorted(daily, key=lambda r: r["date"]):
        iso = row["date"]
        actual = truth.get(iso)
        if actual is None:
            continue
        y, m, d = (int(x) for x in iso.split("-"))
        from datetime import date as _date, timedelta as _td

        prior = (_date(y, m, d) - _td(days=1)).isoformat()
        regime = offshore_regime(off_by_day.get(prior))
        days.append(
            Day(
                date=iso,
                pred=float(row["lstm"]),
                actual=integer_settlement_high_f(actual),
                regime=regime,
            )
        )
    return days


def _cohort_key(strategy: str):
    if strategy == "temp":
        return lambda day: predicted_temperature_cohort(day.pred)
    if strategy == "regime":
        return lambda day: day.regime
    return lambda day: "all"  # global


def score(
    days: list[Day],
    strategy: str,
    *,
    window: int | None,
    cap: float = CAP_F,
    shrink: float = SHRINK_K,
    restrict: set[str] | None = None,
) -> list[tuple[Day, float, float]]:
    """Rolling-origin scored predictions for a de-bias strategy. window=None = expanding.

    ``cap``/``shrink`` parameterize the correction cap and shrink-to-global strength;
    ``restrict`` limits the correction to those cohort keys (e.g. {"warm","hot"}) so
    well-predicted cohorts are left untouched.
    """

    if strategy == "raw":
        return [(day, day.pred, abs(day.pred - day.actual)) for day in days]
    key = _cohort_key(strategy)
    history: list[Day] = []
    out: list[tuple[Day, float, float]] = []
    for day in days:
        base = day.pred
        recent = history[-window:] if window else history
        records = [{"cohort": key(h), "residual": h.actual - h.pred} for h in recent]
        if len(records) >= MIN_HISTORY:
            day_key = key(day)
            if restrict is None or day_key in restrict:
                corrections, global_corr = _cohort_corrections(records, shrink, cap)
                base = day.pred + cap_magnitude(corrections.get(day_key, global_corr), cap)
        out.append((day, base, abs(base - day.actual)))
        history.append(day)
    return out


def _by_cohort(scored: list[tuple[Day, float, float]]) -> dict[str, tuple[int, float, float]]:
    agg: dict[str, list[tuple[float, float]]] = {c: [] for c in COHORTS}
    for day, corrected, abserr in scored:
        agg[settled_cohort(day.actual)].append((abserr, corrected - day.actual))
    out = {}
    for cohort, vals in agg.items():
        if not vals:
            continue
        n = len(vals)
        mae = sum(a for a, _ in vals) / n
        bias = sum(b for _, b in vals) / n
        out[cohort] = (n, mae, bias)
    return out


def _overall_mae(scored) -> float:
    return sum(a for _, _, a in scored) / len(scored)


def _paired_warm(a: list, b: list) -> tuple[float, int, int]:
    """Paired regime-vs-temp on warm settled days: mean abserr delta (a-b), wins, n."""

    deltas = [
        (da[2] - db[2])
        for da, db in zip(a, b)
        if settled_cohort(da[0].actual) == "warm"
    ]
    if not deltas:
        return (0.0, 0, 0)
    wins = sum(1 for d in deltas if d < 0)  # regime lower error
    return (sum(deltas) / len(deltas), wins, len(deltas))


def main() -> int:
    days = load_days(DB_PATH, AB_TEST_PATH)
    regime_counts = {c: sum(1 for d in days if d.regime == c) for c in ("offshore", "transitional", "onshore", "unknown")}
    print(f"days={len(days)}  prior-day regime counts={regime_counts}")
    settled = {c: sum(1 for d in days if settled_cohort(d.actual) == c) for c in COHORTS}
    print(f"settled cohorts (CLISFO): {settled}")

    for window_label, window in (("expanding", None), ("45d", 45)):
        print(f"\n================ window={window_label} ================")
        scored = {s: score(days, s, window=window) for s in ("raw", "global", "temp", "regime")}
        print(f"{'strategy':10s} {'overall':>8s} " + " ".join(f"{c+'_mae':>10s}" for c in COHORTS))
        for s in ("raw", "global", "temp", "regime"):
            byc = _by_cohort(scored[s])
            row = " ".join(
                (f"{byc[c][1]:10.3f}" if c in byc else f"{'-':>10s}") for c in COHORTS
            )
            print(f"{s:10s} {_overall_mae(scored[s]):8.3f} {row}")
        # bias by cohort for temp vs regime (warm focus)
        print("  warm-cohort bias:  " + "  ".join(
            f"{s}={_by_cohort(scored[s]).get('warm', (0,0,0))[2]:+.2f}" for s in ("raw","temp","regime")))
        delta, wins, n = _paired_warm(scored["regime"], scored["temp"])
        if n:
            print(f"  PAIRED warm (regime - temp): mean abserr delta={delta:+.3f}F  "
                  f"regime-better {wins}/{n} ({100*wins/n:.0f}%)  [negative delta = regime wins]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
