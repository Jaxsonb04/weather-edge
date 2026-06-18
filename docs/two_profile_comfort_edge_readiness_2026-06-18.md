# Two-profile collapse + comfortable far-tail NO + readiness gauge

**Date:** 2026-06-18 · **Scope:** profile simplification, the comfort-edge entry
rule, a 5-minute scan cadence, and a real-money readiness signal. All changes
are paper-only; the real-money gate is unchanged and not yet passed.

## Why we were "losing" (live `strategy_research.json`, 2026-06-18 08:35 UTC)

The book was essentially flat, not bleeding: equity **$998.74** of $1,000
(cumulative −$1.26 all-time; +$0.28 realized over the Jun 12–18 window, 66.7% hit
rate). The signal was *where* the losses came from:

| Loss | Bin | Side | Notes |
|---|---|---|---|
| KXHIGHTSFO-26JUN14-**B74.5** | 74–75° | NO | near the predicted high |
| KXHIGHTSFO-26JUN14-**B76.5** | 76–77° | NO | near the predicted high |
| KXHIGHTSFO-26JUN17-**B72.5** | 72–73° | NO | near the predicted high |

Every loser was a **NO bet on a bin next to the forecast**. With a **2.46°F mean
forecast error**, a ~2°-wide near-forecast bin is a coin flip, and the forecaster
is anti-calibrated on the warm days these lived on (warm Brier ~0.96). Betting NO
**comfortably far** from the forecast (predict 75 → NO on ≤65 / ≥85) is robust to
both the error and the warm-day miscalibration — the engine was under-using those
and over-trading the coin-flip center. Also: 100% of trades were NO (zero YES),
and `exploratory` was barely a second collector (1,103 signals vs fast-feedback's
11,046), which motivated merging the two collectors.

## What changed

1. **Two profiles only.** `live` (real-money-intent exploiter, paper-only until
   ready) and `research` (the single loose, tiny-size collector, merged from
   `exploratory` + `fast-feedback`). `conservative` is removed as a selectable
   profile (the strict `StrategyConfig()` baseline stays internal for tests).
   Legacy names alias to the survivors and stored paper books are migrated on
   read, so accumulated AWS history rolls up correctly. (`config.py`, `db.py`
   `PAUSE_THRESHOLDS` + `_migrate_legacy_profile_names`, `strategy_research.py`,
   `cli.py`, dashboard JS, env CSV.)

2. **Comfortable far-tail NO entry** on `live` (`risk.py`). NO bets are gated and
   sized by distance from the point forecast: near-forecast coin-flip NO bets are
   blocked, genuine far-tail NO bets are sized up. The band is uncertainty-scaled
   (multiple of the day's source spread, floored to ~3°F block / ~6°F full). The
   positive after-fee `edge_lcb` floor and all caps still bind, so it never
   admits or enlarges a negative-EV bet. `research` keeps it off to collect the
   full opportunity set.

3. **Every 5 minutes.** `sfo-kalshi-paper-scan.timer` moved 15 → 5 minutes; that
   job live-fetches the order books and makes entries, so a newly-listed far-tail
   bracket is acted on within ~5 minutes. (The 5-min dashboard refresh already
   live-fetched; the docs were corrected to say so.)

4. **Real-money readiness gauge.** `backtest_rescore.compute_real_money_readiness`
   collapses the live walk-forward rescore + per-cohort calibration into a single
   percentage + per-check breakdown, surfaced as a Strategy Lab card. The bar is
   the project's codified gate: positive after-fee day-clustered ROI lower bound
   and log-growth/day, per side and per traded cohort, over ≥30 independent days,
   traded-cohort Brier < 0.25, tight calibration gap. Checks fail closed; the
   percentage shows progress, READY only when everything passes. Judges `live`
   only.

## Validation status

Unit/integration tests cover the merge + migration, the comfort gate/sizing and
its EV-floor guarantee, and the readiness verdict (291 passing). The **real-money
gate is unchanged and NOT passed** — today's live `live` book has ~6 independent
days against a 30-day floor and the normal-cohort Brier is still ~0.54. The
comfort rule and the merged collector must accumulate to the readiness threshold
before any real-money step-up is considered.
