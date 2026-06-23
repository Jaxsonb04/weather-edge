"""Phase 2 step 1: fit the market-overconfidence recalibration slope theta on OUR data.

Research (arXiv 2602.19520) reports Kalshi weather markets are over-confident at
short horizons (logistic-recalibration slope theta < 1), but its "Weather" bucket
mixes temperature with precip/natural-events and gives no CIs — so we re-estimate
theta on our own KXHIGHTSFO history before trusting it (plan Phase 2).

Method: for each historical event-day, take each bin's day-ahead market-implied
probability from the Kalshi candle history (yes bid/ask mid, de-vigged across the
ladder exactly as probability._market_implied_probabilities does), pair it with the
realized YES outcome under the CLISFO settlement, and fit a 2-parameter logistic
recalibration  P(YES) = sigma(alpha + theta * logit(p_market))  by Newton-Raphson.
theta < 1  => market over-confident (prices too extreme; the engine should de-extreme
via p* = sigma(theta * logit p)). Reported overall, per horizon bucket, per cohort.

Pure stdlib. Read-only. Run from trading/:  python -m sfo_kalshi_quant.theta_fit
"""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .config import DEFAULT_DB_PATH, DEFAULT_FORECASTER_ROOT, temperature_cohort

HORIZONS = ((0.0, 24.0, "<=24h"), (24.0, 48.0, "24-48h"))
NEAR_TOLERANCE_H = 8.0   # a candle must be within this of the target lead to count
MIN_BINS = 4             # need a well-formed ladder to de-vig
CLAMP = 1e-4


def _weather_db() -> Path:
    return DEFAULT_FORECASTER_ROOT / "weather.db"


def _to_epoch(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value)
    try:
        return int(float(text))
    except ValueError:
        pass
    try:
        return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def resolves_yes(high: int, strike_type: str | None, floor_strike, cap_strike) -> bool:
    st = (strike_type or "").lower()
    if st == "greater":  # "X or above"
        return floor_strike is not None and high > float(floor_strike)
    if st == "less":  # "X or below"
        return cap_strike is not None and high < float(cap_strike)
    if st == "between":
        return floor_strike is not None and cap_strike is not None and float(floor_strike) <= high <= float(cap_strike)
    return False


def _clisfo_truth(weather_db: Path) -> dict[str, int]:
    if not weather_db.exists():
        return {}
    with sqlite3.connect(weather_db) as conn:
        return {
            d: int(t)
            for d, t in conn.execute(
                "SELECT local_date, max_temperature_f FROM clisfo_settlements WHERE max_temperature_f IS NOT NULL"
            )
        }


def _markets(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """event_ticker -> list of bin dicts (ticker, strikes, close_ts, target_date)."""

    by_event: dict[str, list[dict]] = defaultdict(list)
    for row in conn.execute(
        "SELECT ticker, event_ticker, target_date, close_time, strike_type, floor_strike, cap_strike "
        "FROM dataset_kalshi_markets"
    ):
        ticker, event, target_date, close_time, strike_type, floor_strike, cap_strike = row
        close_ts = _to_epoch(close_time)
        if close_ts is None:
            continue
        by_event[event].append(
            {
                "ticker": ticker,
                "target_date": target_date,
                "close_ts": close_ts,
                "strike_type": strike_type,
                "floor_strike": floor_strike,
                "cap_strike": cap_strike,
            }
        )
    return by_event


def _candle_mid_near(conn: sqlite3.Connection, ticker: str, target_ts: int) -> float | None:
    """De-vig-input: yes bid/ask mid from the candle nearest target_ts (within tolerance)."""

    row = conn.execute(
        """
        SELECT end_period_ts, yes_bid_close, yes_ask_close
        FROM dataset_kalshi_candles
        WHERE ticker = ?
        ORDER BY abs(end_period_ts - ?) ASC
        LIMIT 1
        """,
        (ticker, target_ts),
    ).fetchone()
    if row is None:
        return None
    ts, bid, ask = row
    if abs(ts - target_ts) > NEAR_TOLERANCE_H * 3600:
        return None
    vals = [v for v in (bid, ask) if v is not None]
    if not vals:
        return None
    return max(0.0, min(1.0, sum(float(v) for v in vals) / len(vals)))


def _logit(p: float) -> float:
    p = min(1.0 - CLAMP, max(CLAMP, p))
    return math.log(p / (1.0 - p))


def fit_logistic(zs: list[float], ys: list[float], iters: int = 50) -> tuple[float, float]:
    """Newton-Raphson 2-param logistic: P(y)=sigma(a + th*z). Returns (alpha, theta)."""

    a, th = 0.0, 1.0
    for _ in range(iters):
        g0 = g1 = h00 = h01 = h11 = 0.0
        for z, y in zip(zs, ys):
            lin = max(-30.0, min(30.0, a + th * z))
            p = 1.0 / (1.0 + math.exp(-lin))
            w = p * (1.0 - p)
            r = p - y
            g0 += r
            g1 += r * z
            h00 += w
            h01 += w * z
            h11 += w * z * z
        det = h00 * h11 - h01 * h01
        if abs(det) < 1e-12:
            break
        da = (h11 * g0 - h01 * g1) / det
        dth = (-h01 * g0 + h00 * g1) / det
        a -= da
        th -= dth
        if abs(da) + abs(dth) < 1e-9:
            break
    return a, th


def collect_pairs() -> list[dict]:
    """(p_market de-vigged, outcome, horizon label, cohort) over all event-days/horizons."""

    truth = _clisfo_truth(_weather_db())
    conn = sqlite3.connect(DEFAULT_DB_PATH)
    pairs: list[dict] = []
    try:
        by_event = _markets(conn)
        for event, bins in by_event.items():
            target_date = bins[0]["target_date"]
            settled = truth.get(target_date)
            if settled is None:
                continue
            cohort = temperature_cohort(float(settled))
            close_ts = max(b["close_ts"] for b in bins)
            for lo, hi, label in HORIZONS:
                target_ts = close_ts - int((lo + hi) / 2 * 3600)
                mids = {}
                for b in bins:
                    mid = _candle_mid_near(conn, b["ticker"], target_ts)
                    if mid is not None:
                        mids[b["ticker"]] = mid
                total = sum(mids.values())
                if len(mids) < MIN_BINS or total <= 0:
                    continue
                for b in bins:
                    if b["ticker"] not in mids:
                        continue
                    p_devig = mids[b["ticker"]] / total
                    outcome = 1.0 if resolves_yes(settled, b["strike_type"], b["floor_strike"], b["cap_strike"]) else 0.0
                    pairs.append({"p": p_devig, "y": outcome, "horizon": label, "cohort": cohort, "event": event})
    finally:
        conn.close()
    return pairs


def _fit_group(group: list[dict]) -> tuple[int, float, float, float]:
    """Returns (n, alpha, theta, brier) for a group of pairs."""

    zs = [_logit(g["p"]) for g in group]
    ys = [g["y"] for g in group]
    a, th = fit_logistic(zs, ys)
    brier = sum((g["p"] - g["y"]) ** 2 for g in group) / len(group)
    return len(group), a, th, brier


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))


def _bin_center(strike_type: str | None, floor_strike, cap_strike) -> float | None:
    st = (strike_type or "").lower()
    if st == "between" and floor_strike is not None and cap_strike is not None:
        return (float(floor_strike) + float(cap_strike)) / 2.0
    if st == "greater" and floor_strike is not None:
        return float(floor_strike) + 1.0  # ">floor": tail centered just above
    if st == "less" and cap_strike is not None:
        return float(cap_strike) - 1.0  # "<cap": tail centered just below
    return None


def collect_event_days() -> list[dict]:
    """Day-ahead per-event-day records: de-vigged bin probs + outcomes + bin centers,
    the market-IMPLIED high (trade-time-known) and its cohort, and the settled cohort."""

    truth = _clisfo_truth(_weather_db())
    conn = sqlite3.connect(DEFAULT_DB_PATH)
    out: list[dict] = []
    try:
        by_event = _markets(conn)
        for event, bins in by_event.items():
            target_date = bins[0]["target_date"]
            settled = truth.get(target_date)
            if settled is None:
                continue
            close_ts = max(b["close_ts"] for b in bins)
            target_ts = close_ts - int(12 * 3600)  # mid of the <=24h day-ahead bucket
            mids, centers = {}, {}
            for b in bins:
                mid = _candle_mid_near(conn, b["ticker"], target_ts)
                if mid is None:
                    continue
                mids[b["ticker"]] = mid
                centers[b["ticker"]] = _bin_center(b["strike_type"], b["floor_strike"], b["cap_strike"])
            total = sum(mids.values())
            if len(mids) < MIN_BINS or total <= 0:
                continue
            recs = []
            for b in bins:
                if b["ticker"] not in mids:
                    continue
                p = mids[b["ticker"]] / total
                y = 1.0 if resolves_yes(settled, b["strike_type"], b["floor_strike"], b["cap_strike"]) else 0.0
                recs.append({"p": p, "y": y, "center": centers[b["ticker"]]})
            implied_high = sum(r["p"] * r["center"] for r in recs if r["center"] is not None)
            out.append(
                {
                    "date": target_date,
                    "bins": recs,
                    "implied_high": implied_high,
                    "implied_cohort": temperature_cohort(implied_high),
                    "settled_cohort": temperature_cohort(float(settled)),
                }
            )
    finally:
        conn.close()
    return sorted(out, key=lambda e: e["date"])


def walk_forward_validate(event_days: list[dict], *, min_train_days: int = 30, min_cohort: int = 40) -> dict:
    """Leakage-safe OOS test: fit theta on PRIOR event-days (per market-implied cohort,
    falling back to global when thin), apply p* = sigmoid(theta * logit p) to the current
    day, renormalize, and accumulate Brier/log-loss for raw vs recalibrated market probs."""

    prior_all: list[tuple[float, float]] = []
    prior_cohort: dict[str, list[tuple[float, float]]] = defaultdict(list)
    n = 0
    raw_b = recal_b = raw_ll = recal_ll = 0.0
    thetas_used: list[float] = []
    for idx, ed in enumerate(event_days):
        if idx >= min_train_days and len(prior_all) >= 20:
            _, th_g = fit_logistic([z for z, _ in prior_all], [y for _, y in prior_all])
            cps = prior_cohort.get(ed["implied_cohort"], [])
            theta = fit_logistic([z for z, _ in cps], [y for _, y in cps])[1] if len(cps) >= min_cohort else th_g
            theta = max(0.1, min(3.0, theta))
            thetas_used.append(theta)
            recal = [_sigmoid(theta * _logit(b["p"])) for b in ed["bins"]]
            s = sum(recal)
            recal = [r / s for r in recal] if s > 0 else [b["p"] for b in ed["bins"]]
            for b, rp in zip(ed["bins"], recal):
                y = b["y"]
                raw_b += (b["p"] - y) ** 2
                recal_b += (rp - y) ** 2
                raw_ll += -math.log(max(b["p"] if y else 1 - b["p"], 1e-12))
                recal_ll += -math.log(max(rp if y else 1 - rp, 1e-12))
                n += 1
        for b in ed["bins"]:
            z = _logit(b["p"])
            prior_all.append((z, b["y"]))
            prior_cohort[ed["implied_cohort"]].append((z, b["y"]))
    if n == 0:
        return {"n": 0}
    return {
        "n": n,
        "raw_brier": raw_b / n,
        "recal_brier": recal_b / n,
        "raw_logloss": raw_ll / n,
        "recal_logloss": recal_ll / n,
        "mean_theta": sum(thetas_used) / len(thetas_used) if thetas_used else 1.0,
    }


def main() -> int:
    pairs = collect_pairs()
    print(f"theta-fit pairs (de-vigged market prob vs CLISFO YES): {len(pairs)}")
    if not pairs:
        print("no pairs — is the Kalshi candle backfill present? run dataset-backfill --kalshi-candles")
        return 1

    def report(label: str, group: list[dict]) -> None:
        if len(group) < 20:
            print(f"  {label:24s} n={len(group):4d}  (too few to fit)")
            return
        n, a, th, brier = _fit_group(group)
        flag = "OVER-confident (fade)" if th < 0.95 else ("under-confident" if th > 1.05 else "~calibrated")
        print(f"  {label:24s} n={n:4d}  theta={th:5.2f}  alpha={a:+5.2f}  brier={brier:.3f}  -> {flag}")

    print("\n# By horizon")
    for _, _, label in HORIZONS:
        report(label, [p for p in pairs if p["horizon"] == label])
    print("\n# Day-ahead (<=24h) by settled cohort")
    near = [p for p in pairs if p["horizon"] == "<=24h"]
    for cohort in ("cold_below_60f", "normal_60_69f", "warm_70_79f", "hot_80f_plus"):
        report(cohort, [p for p in near if p["cohort"] == cohort])
    print("\n# Overall (all horizons)")
    report("all", pairs)

    event_days = collect_event_days()
    print("\n# Day-ahead theta by MARKET-IMPLIED-high cohort (trade-time-actionable key)")
    by_impl: dict[str, list[dict]] = defaultdict(list)
    for ed in event_days:
        for b in ed["bins"]:
            by_impl[ed["implied_cohort"]].append({"p": b["p"], "y": b["y"]})
    for cohort in ("cold_below_60f", "normal_60_69f", "warm_70_79f", "hot_80f_plus"):
        report(cohort, by_impl.get(cohort, []))

    print("\n# OUT-OF-SAMPLE validation: recalibrated vs raw market prob (walk-forward, leakage-safe)")
    wf = walk_forward_validate(event_days)
    if wf.get("n"):
        bimp = 100 * (wf["raw_brier"] - wf["recal_brier"]) / wf["raw_brier"]
        limp = 100 * (wf["raw_logloss"] - wf["recal_logloss"]) / wf["raw_logloss"]
        print(f"  scored bins={wf['n']}  mean applied theta={wf['mean_theta']:.2f}")
        print(f"  Brier    raw={wf['raw_brier']:.4f} -> recal={wf['recal_brier']:.4f}  ({bimp:+.1f}%)")
        print(f"  LogLoss  raw={wf['raw_logloss']:.4f} -> recal={wf['recal_logloss']:.4f}  ({limp:+.1f}%)")
        verdict = "HELPS" if wf["recal_brier"] < wf["raw_brier"] else "does NOT help"
        print(f"  => recalibration {verdict} the market signal out-of-sample")

    print("\nNote: theta is the recalibration slope for p* = sigmoid(theta * logit p).")
    print("theta<1 => the market is over-confident at that horizon/cohort; de-extreme toward climatology.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
