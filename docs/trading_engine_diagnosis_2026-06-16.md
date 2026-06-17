<!-- Generated 2026-06-16 by the trading-engine-diagnosis workflow: 11 agents, parallel code evidence + adversarial verification + academic grounding. All findings cross-checked against live production strategy_research.json. -->

# WeatherEdge Diagnostic Report: Why $5 Bets, the +35% Badge, and the 100c Exits

**Prepared for:** WeatherEdge owner
**Date:** 2026-06-16
**Scope:** Five verified findings on position sizing, exit economics, trade frequency, and UI, each cross-checked against the live code/data and grounded in the academic literature on Kelly sizing, optimal stopping, and prediction-market microstructure.

---

## 1. TL;DR

- **(a) Why ~$5 max on $1000:** Not a Kelly artifact. Your per-position **dollar cap binds 100% of the time** because the Kelly spend budget on a typical favorite (~$44–67) is ~9× larger than the cap ($5 balanced / $10 conservative). `fractional_kelly` is therefore **inert** — it never gets to speak. You are flat-betting ~1% of full Kelly, so **profit is bounded by stake, not by edge**. Realized stakes averaged **$1.19/trade**; combined realized PnL is **−$0.17 on $1000**. Fix the cap (and the frozen-$1000 bug), not the Kelly multiplier.

- **(b) Is "+35% fixed" a bug?** The **number is not a bug, but the UI is misleading.** 35% is a *forward-looking rule target* (the NO take-profit constant), stamped on **every** NO card regardless of outcome — including losers down to −85.7%. **Zero** of 19 closed positions actually realized ~35%. Real realized ROIs span **−85.7% to +36.6%**. So "+35%" is a label artifact, not an economic result. (Display bug — SAFE to fix.)

- **(c) Is "always sells at 100c / every profit-exit >99%" a bug?** **No — it is a structural consequence of buying expensive favorites with a percentage take-profit.** For a favorite bought at cost `c`, the take-profit target `c·(1+T)` exceeds the maximum achievable net exit (0.98 at the 99c bid cap) whenever `c > 0.98/(1+T)`. **13 of 16 NO positions** have `c > 0.726`, making the intraday take-profit **mathematically unhittable** — those winners can only ride to the **$1.00 settlement**. The engine already knows this and stores `take_profit_bid=None`. Not a bug; a design consequence.

- **(d) Can we trade more often?** **Yes — modestly and safely.** In the live snapshot, **0 of 24** candidates were approved. The single most-binding gate is the lower-bound-edge floor `min_edge_lcb` (blocks 19/24, sole blocker on all 4 genuine positive-edge candidates). Loosening it **−0.030 → −0.070 in the research profile only** recovers exactly **2 positive-EV trades (0% → 8%)** without admitting a single negative point-edge bet. Eight other rejections are settled/stale markets that must stay blocked.

- **(e) Is the "buy-30c-sell-60c" model possible here?** **Not with the current entry distribution.** That model requires **cheap-tail entries** (`cost < ~0.65`) where a percentage take-profit is actually reachable. Today entries cluster at **0.74–0.91 favorites**, which can only resolve to settlement. Buying favorites is *directionally* correct under the favorite-longshot bias (Snowberg-Wolfers: favorites −5.5% vs longshots −61%), but the **double-the-money pattern is a different trade** — it needs the candidate generator to source cheaper contracts, not an exit-rule change.

---

## 2. Finding 1 — Microscopic Position Sizing (the ~$5 / $1.19 cap)

### 2.1 What's happening in the code

The sizing chain (`trading/sfo_kalshi_quant/risk.py:149-161`) is:

```
kelly        = kelly_fraction_spent(p, cost)      # fees.py:99-111  -> (p - cost)/(1 - cost)
kelly       *= fractional_kelly                    # risk.py:154
risk_budget  = bankroll * max_position_risk_pct    # risk.py:155
kelly_budget = bankroll * kelly                    # risk.py:156
spend_budget = min(risk_budget, kelly_budget)      # risk.py:157  <-- the binding min()
contracts    = spend_budget / cost                 # risk.py:161
```

The Kelly fraction itself is **correct** and is exactly Thorp's binary-contract special case:

$$ f^{*} = \frac{p - c}{1 - c} $$

This is the Kelly-optimal fraction of bankroll to commit to the *purchase cost* of a contract that costs `c` and pays `1`. It derives from Thorp's general-odds formula `f* = (bp − q)/b` with odds `b = (1−c)/c`, maximizing the log-growth objective `g(f) = p·ln(1+bf) + q·ln(1−f)` (Thorp 2006). Kelly's 1956 original even-money root is `f* = p − q` ("bet your edge").

### 2.2 The math: the cap binds, Kelly never speaks

Worked example — a favorite at **p = 0.90, ask = 0.80**, fee = `ceil(0.07·0.8·0.2) = 0.02`, so **cost = 0.82**:

- **Full classic Kelly:** `b = 0.18/0.82 = 0.2195`, `q = 0.10`, `f* = (0.2195·0.9 − 0.10)/0.2195 = 0.4444` → full Kelly would wager **44.4%** of bankroll.
- Code's spend fraction: `kelly_fraction_spent = (0.90 − 0.82)/(1 − 0.82) = 0.08/0.18 = 0.4444`.
- **Balanced profile** (`fractional_kelly=0.10`, `max_position_risk_pct=0.005`): `kelly_budget = 1000·0.4444·0.10 = $44.44`, but `risk_budget = 1000·0.005 = $5`. → `spend = min($5, $44.44) = $5`. **The $5 cap binds.** Contracts = `5/0.82 = 6`, $risk ≈ $4.92.
- **Conservative** (`0.15/0.01`): `kelly_budget = $66.67` vs `risk_budget = $10` → cap binds at $10.

I checked a full grid of favorites (`p` from 0.70 to 0.99): the $5 cap binds on **100% of them** (the smallest Kelly budget, $6.25, still exceeds $5). **`fractional_kelly` is genuinely inert while the cap binds**, and because both `db.py:942` (settle) and `db.py:1006` (close) are *linear in contracts*, **PnL scales linearly with the stake cap**.

Effective Kelly fraction: balanced `k = $5/$444 = 0.0113` — you are betting **~1.1% of full Kelly** (growth ≈ `k(2−k)` = **2.2% of the maximum achievable growth rate**). Realized stakes confirm this: min/avg/max risk = **$0.13 / $1.19 / $2.74**; balanced 2 resolved +$0.27 (ROI +15.6%), fast-feedback 17 resolved −$0.44 (ROI −2.1%), **combined realized −$0.17**.

> **Note on counts:** the live JSON shows **19 resolved** closed positions (not 23 — that figure conflated order count with resolved count). The balanced +15.6% ROI rests on only **2 resolved trades**, which makes the edge *more* noise-dominated, not less. This reinforces the "validate before leveraging" caution below.

### 2.3 Why fractional Kelly is the right *frame* but the wrong *knob*

The literature is unambiguous that you should bet a **fraction** of full Kelly — the question is which lever moves it. Half-Kelly is the canonical bargain because **growth is flat near the optimum but variance is not**: betting half Kelly retains **~75% of the maximum growth rate** while **cutting log-wealth variance to ~25%** (variance scales with `f²`). Overbetting is asymmetrically catastrophic — MacLean, Thorp & Ziemba prove `g(2f*) ≈ 0`:

> "the growth rate becomes zero plus the risk free rate when one bets exactly twice the Kelly wager. Hence it never pays to bet more than the Kelly strategy… As you exceed the Kelly bets more and more, risk increases and long term growth falls." — MTZ, *Good and Bad Properties of the Kelly Criterion*

And estimation error in `p` (a *mean* estimate) is the dominant risk: MTZ cite Chopra-Ziemba that "Errors in means versus errors in variances were about **20:2:1** in importance." Your `p` is a weather-model estimate, so sizing on a **lower confidence bound of `p`** (`kelly_lcb_weight`) is exactly right and should be kept.

### 2.4 Recommendation, projected $ impact, and risk-of-ruin

**The lever is `max_position_risk_pct`, not `fractional_kelly`** (which is inert while the cap binds), and **only on the positive-ROI balanced profile** after walk-forward validation:

| Parameter | Current (balanced) | Proposed | Rationale |
|---|---|---|---|
| `max_position_risk_pct` | 0.005 ($5) | **0.02–0.03 ($20–30)** | Lets Kelly become the active sizer; cap becomes a tail guard, not the throttle |
| `max_event_risk_pct` | 0.015 | 0.04 | Scales with per-position cap |
| `max_target_exposure_pct` | 0.025 | 0.06 | Scales with per-position cap |
| `max_contracts_per_market` | 10 | 40 | Removes secondary clamp |
| notional base | frozen $1000 | **live bankroll** | Mandatory for compounding (Kelly requires sizing off current wealth) |

**Growth-vs-security tradeoff, quantified** (growth ≈ `g*·k·(2−k)`, variance ≈ `k²·σ²`):

| Fraction k of full Kelly | % full-Kelly growth | % full-Kelly variance | P(50% drawdown) ≈ `a^(2/k−1)` |
|---|---|---|---|
| 0.15 (current intent) | ~28% | ~2% | negligible |
| **0.045–0.068 (proposed $20–30 cap)** | ~9–13% | ~0.3% | **well under 0.1%** |
| 0.50 (half-Kelly) | **75%** | 25% | ~12.5% |
| 1.00 (full) | 100% | 100% | 50% |
| 2.00 (overbet) | **~0%** | 400% | the cliff |

**Projected impact:** at a $20–30 cap the *same trade flow* lifts balanced realized PnL from **+$0.27 to roughly +$1.08 to +$1.62** (4–6× linear scaling), with **sub-0.1% deep-drawdown probability**. A true Kelly bettor "never risks ruin" (MTZ Good Property #4) because the bet shrinks with the bankroll; at k ≤ 0.07 you are far on the safe side. **The one inviolable rule: never exceed full Kelly.**

**Critical gate:** this only amplifies a *true* edge. Fast-feedback's negative ROI would scale to a **larger loss**, so **gate the cap increase to the balanced/primary profile only**, and only after a walk-forward, after-fee backtest confirms the +15.6% is real and not 2-trade noise.

**Citations:** Kelly (1956), *Bell System Technical Journal* 35(4):917–926 — https://www.princeton.edu/~wbialek/rome/refs/kelly_56.pdf · Thorp (2006), "The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market" — https://gwern.net/doc/statistics/decision/2006-thorp.pdf · MacLean, Thorp & Ziemba (2010), "Good and Bad Properties of the Kelly Criterion" — https://www.stat.berkeley.edu/~aldous/157/Papers/Good_Bad_Kelly.pdf

---

## 3. Finding 2 — The +35% Ceiling & the Unreachable Take-Profit

### 3.1 The reachability math (a hard ceiling, no behavioral assumptions)

A long binary entered at cost `c` can settle at most at $1.00, so the **maximum return is `(1−c)/c`** — bounded by residual upside. Separately, the engine caps the intraday exit bid at 0.99, and the taker fee there is `ceil_to_cent(0.07·0.99·0.01) = $0.01`, so the **maximum achievable net exit is `NET_99 = 0.99 − 0.01 = 0.98`** (`fees.py:18-36`).

The take-profit fires intraday only if `net_exit ≥ c·(1+T)` (`cli.py:1979-1986`). Since `net_exit ≤ 0.98`, the TP is **reachable only when**:

$$ c \le \frac{0.98}{1+T} $$

| Side | `T` | Break-even `c` | Above this, TP is impossible |
|---|---|---|---|
| NO | 0.35 | `0.98/1.35 =` **0.7259** | `c > 0.726` |
| YES | 0.50 | `0.98/1.50 =` **0.6533** | `c > 0.653` |
| Default | 0.40 | `0.98/1.40 =` **0.7000** | `c > 0.700` |

**Worked example, NO at c = 0.85:** TP target net = `0.85·1.35 = 1.1475`, which exceeds **both** the 0.98 net ceiling **and** the $1.00 hard ceiling — the bid can *never* reach it. The contract can only resolve at settlement: payout 1.00 → `realized_pnl = 1·(1−0.85) = $0.15` (matches JSON exactly).

Applied to the **16 real NO costs** (0.548, 0.67, 0.71, 0.755, 0.77, 0.79, 0.795, 0.803, 0.82, 0.84, 0.84, 0.85, 0.85, 0.907, 0.91, 0.91): **13 of 16 have `c > 0.726` → TP mathematically impossible**; only 3 (0.548, 0.67, 0.71) can ever hit it intraday. The cross-check is exact: **0/19 mismatches** between this break-even prediction and the engine's own `take_profit_bid=None` flag.

> The "35" default itself comes from this ceiling: at `c = 0.74`, `(1−0.74)/0.74 = 35.1%`. The default was set to the max return of the cheapest favorite the engine expects to buy — which is precisely why it's unreachable for everything more expensive.

### 3.2 Is it a bug or a design flaw?

**Neither a coding bug nor a PnL bug — it is a *framing* flaw.** The engine correctly encodes the unreachability (`strategy_research.py:1816-1822` returns `None`; `:1923` computes `take_profit_net = cost·(1+T)`). The settled winners already collect the **full `(1−c)` at $1.00, the maximum possible outcome** — so "fixing" the exit would *not* improve realized PnL and could slightly *reduce* it by exiting early for less than the full spread.

The deeper economic point (the literature) is that for a **fairly-priced binary, no threshold exit beats holding to settlement on an EV basis**. A correctly-priced contract is a bounded martingale converging to $0/$1; by the optional-stopping theorem, `E[X_τ] = X_0` for *any* stopping rule. **Kaminski & Lo (2014)** prove the "stopping premium" is **negative under the random-walk hypothesis**:

> "Under the Random Walk Hypothesis, simple 0/1 stop-loss rules always decrease a strategy's expected return, but in the presence of momentum, stop-loss rules can add value." — Kaminski & Lo, *Journal of Financial Markets* 18:234–254

A percentage take-profit/stop-loss is therefore defensible only as a **risk/liquidity control under a non-EV (Kelly/log-utility) objective**, not as a return enhancer. For an edge-having holder of a converging weather binary, **holding to resolution weakly dominates any premature exit on EV**.

### 3.3 Fix options (all cosmetic/operational, not PnL levers)

1. **Cap the effective TP at the reachable ceiling:** `effective_tp_net = min(c·(1+T), NET_99 − ε)`. Prevents storing impossible targets.
2. **Switch expensive favorites (`c > ~0.73`) from a percentage target to an absolute "capture X cents of the residual spread" rule:** exit when `net_exit ≥ c + α·(0.98 − c)`. This reads as intended for favorites that can only ride to settlement.
3. **Document this in `strategy.md`** so the exit behavior reads as designed, not broken.

**Do not** expect any of these to raise PnL. The real lever is upstream (Findings 1 and 4).

**Citations:** Kaminski & Lo (2014), "When Do Stop-Loss Rules Stop Losses?" *J. Financial Markets* 18:234–254 — https://dspace.mit.edu/handle/1721.1/114876 · Optional-stopping theorem (standard) · MacLean/Thorp/Ziemba (2010) for the growth-vs-EV distinction — https://www.stat.berkeley.edu/~aldous/157/Papers/Good_Bad_Kelly.pdf

---

## 4. Finding 3 — Winners Settle at $1.00 ("sells at 100c")

### 4.1 Settlement path vs intraday path

There are exactly two close paths in the code:

- **`db.py:932-995` `settle_paper_orders`:** `realized_pnl = contracts·((1.0−cost) if wins else −cost)`. The winner is paid the **full $1.00 spread at settlement**; `exit_price` stays `NULL`, status `PAPER_SETTLED`. This is the *only* path for the unreachable-TP favorites.
- **`db.py:997-1025` `close_paper_order`:** `realized_pnl = contracts·(exit_price − exit_fee − entry_cost)`, requiring `0 < exit_price < 1`. The **only** path that records a sub-$1.00 exit.

In the JSON, the **9 PAPER_SETTLED winners are all NO** (`resolved_yes=0`, `exit_price=null`, `take_profit_bid=None`) — every one rode to $1.00 because its cost (0.74–0.91) put the TP out of reach. The **10 PAPER_CLOSED** had real exit prices (0.02, 0.06, 0.09, 0.12, 0.16, 0.36, 0.47, 0.52, 0.76, 0.98); only **2 were profitable**, and both were NO bought **cheap** (cost 0.548 and 0.71 ≤ 0.726 break-even). All 9 settled winners reconcile exactly: `realized_pnl == contracts·(1−cost)`.

So "always sells at 100c" is literally true **for the favorites** — and it is the *best possible outcome* for them, not a leak. The per-contract upside is just structurally small: `(1−c)` = $0.09–$0.26 while downside is the full $0.74–$0.91.

### 4.2 Favorite-longshot context

Buying favorites is the *directionally correct* instinct. The favorite-longshot bias is the most robust regularity in these markets, and it favors the favorite side. **Snowberg & Wolfers (2010):**

> "longshots are overbet, while favorites are underbet… the rate of return to betting on horses with odds of 100/1 or greater is about **−61%**, betting randomly yields average returns of **−23%**, while betting the favorite in every race yields losses of only **−5.5%**."

But two caveats apply directly to WeatherEdge. First, **price = probability** in an efficient market — **Wolfers & Zitzewitz (2004):** "The price on a winner-take-all market represents the market's expectation of the probability that an event will occur," so a fairly-priced 0.74–0.91 favorite has **~zero edge before fees, negative after**. Second, the bias is **conditional on the market being noise-dominated** — **Ottaviani & Sørensen (2010)** show it "depends on the ratio of private information to noise" and can weaken or reverse when bettors are well-informed. Your favorite-side edge is an *informational claim* about the weather crowd, not a structural payout.

### 4.3 Why "buy-30c-sell-60c" isn't what this strategy does — and how to enable it

The double-the-money pattern requires **cheap-tail entries** (`cost < ~0.65`) where a percentage take-profit is *reachable* (at `c = 0.30`, max return `(1−0.30)/0.30 = +233%`, so a 100% TP fires easily). Your engine instead clusters at **0.74–0.91 favorites**, which can only ride to settlement for a +9–35% max. **This is a candidate-sourcing question, not an exit-rule question.**

To enable it: change the **candidate generation / edge gate** to surface cheap contracts where `(1−c)/c` is large and a percentage TP is reachable — i.e. loosen toward cheaper YES tails *with genuine positive point-edge*, not toward more expensive NO favorites. **Caution:** do **not** chase the `+0.23/+0.31` "edge" on the 1–4¢ cheap-tail candidates (#8/#10/#12) — those carry a 0.26–0.32 model-vs-market gap and are exactly the cheap-tail overconfidence the realized 1.9%-vs-8.7% calibration failure already burned.

**Citations:** Snowberg & Wolfers (2010), *J. Political Economy* 118(4):723–746 — https://www.nber.org/system/files/working_papers/w15923/w15923.pdf · Wolfers & Zitzewitz (2004), *J. Economic Perspectives* 18(2):107–126 — https://www.nber.org/papers/w10504 · Ottaviani & Sørensen (2010), *AEJ: Microeconomics* 2(1):58–85 — https://web.econ.ku.dk/sorensen/papers/niaflb.pdf

---

## 5. Finding 4 — 0% Approval / Trade Frequency

### 5.1 The binding-gate tally

The live snapshot has **24 candidates, 0 approved**, all fast-feedback, generated 2026-06-16T23:56Z. Gate appearances across the 24 rejections (`risk.py` evaluate_market):

| Gate | Appears in N of 24 | Sole blocker? |
|---|---|---|
| **`min_edge_lcb` (−0.03)** | **19** | **Yes — on #0, #6, #17, #20 (all positive point-edge)** |
| `min_edge` (point edge ≥ 0.005) | 14 | No |
| ask not tradeable (`0<ask<1`) | 8 | No |
| `cost ≥ 1` | 8 | No |
| `spread_fraction_of_cost` | 4 | No |
| `model_market_gap` (>0.25) | 4 | No |
| `cheap_tail` | 4 | No |
| bid-size / ask-size / forecast-age | 0 | — |

`edge_lcb = side_probability_lcb − cost` (`risk.py:111`); the two edge gates are at `risk.py:113-116`. The lower-bound floor collapses far below the point estimate because `prob_lcb` is penalized for model-vs-market disagreement (`probability.py:228`, `0.35·|model−market|`) plus the conditional-only sample-size widening (`probability.py:208`). **Candidate #6:** `p = 0.812` but `prob_lcb = 0.645` (a 0.167 haircut), dragging `edge_lcb` to **−0.065** even though point edge is **+0.165**.

### 5.2 The fix and the sensitivity math

Loosen `min_edge_lcb` **in the fast-feedback research profile only**:

| `min_edge_lcb` | Approved | Which |
|---|---|---|
| −0.03 (current) | 0 | — |
| −0.05 | 0 | — |
| **−0.07 (proposed)** | **2** | #6 (edge +0.165), #17 (edge +0.048) |
| −0.10 | 2 | (next positive-edge sits at −0.122) |
| −0.15 | 4 | adds #0, #20 |

**Approval rate: 0% → 8% at −0.07.** Both admitted trades have **positive EV not just under model_p but under the more conservative blended posterior** (#6 +0.102, #17 +0.0135) — they are negative *only* under `prob_lcb`. The LCB is a **variance/overconfidence buffer, not the EV sign**, so loosening it does **not** induce negative-EV trading. Per-trade downside is capped at **~$2** (fast-feedback `max_position_risk_pct=0.002`, `max_contracts=3`).

The other 8 rejections are **ask = $1.00 on settled/stale markets** (#1,2,3,4,5,7,9,11) — a **data-freshness bug**: the candidate generator is feeding already-resolved past-date markets into evaluation, polluting the denominator. Filter `ask ≥ 0.999` (and `target_date <= today`) *before* evaluation; that drops the denominator from 24 to ~16, making the honest post-fix rate **2/16 = 12.5%**.

**Citation for keeping the live profiles strict:** `config.py:117-123` documents a 3/190 negative-LCB failure; the balanced/conservative `edge_lcb ≥ 0` floor is the proven defense and **must stay intact** (consistent with the 20:2:1 mean-error sensitivity, MTZ/Chopra-Ziemba).

---

## 6. Finding 5 — Misleading UI

Two genuine display artifacts (both **SAFE** to fix; neither touches economics):

### 6.1 The fixed "+35.0% ROI" badge on every NO card

- `strategy_research.py:1920-1924` / `:1989-1995`: `take_profit_pct` is a **fixed per-side constant** (35 NO / 50 YES), computed for **every** `_paper_row` regardless of outcome (closed positions also flow through `_paper_row` at `:1066`).
- `strategy-lab.html:2469, 2484`: the open-card exit-strip always renders `exitStat('Take profit bid', …)` with detail `+${fmt(row.take_profit_pct,1)}% ROI after exit fee.` → **"+35.0% ROI…" on every NO card.**
- **Reality:** all NO rows carry `take_profit_pct=35.0`, **including the −85.7% losers**; **0 of 19** closed positions actually realized ~35% (`abs(realized_roi − 0.35) < 0.005` matches none). Real ROIs span **−85.7% to +36.6%**.

**Fix:** relabel `strategy-lab.html:2484/2469` from "Take profit bid" / "+35.0% ROI after exit fee" to **"Take-profit target (rule)"** with detail **"Sell rule: exit if mark reaches +35.0%."** Ensure no "+35%" target leaks into the action/closed tables (the card is already open-only at `:2371`). Optionally suppress the badge entirely when `take_profit_bid` is null ("Not reachable before 99c", already at `:2466`).

### 6.2 Duplicated `recent_monitor_actions`

- `strategy_research.py:959-967`: `monitor_rows` selects `paper_monitor_snapshots ORDER BY created_at DESC LIMIT 12` with **no GROUP BY / no per-order dedup**. The monitor writes **one snapshot row per open order per ~2-min cycle** (`db.py:153-168`, `record_monitor_snapshot` `db.py:873`).
- `strategy_research.py:1067-1083`: merges per-snapshot + closed rows, sorts, truncates to 12 — **no dedup by order id**. Result: **8 HOLD rows collapse to only 3 distinct positions** — id19 ×3 (pnl 0.59), id20 ×3 (pnl 0.40), id21 ×2 (pnl 0.11), all `exit_price=0.99`. `strategy-lab.html:2565-2585` renders each as a separate line → the "repeated 0.59/0.40/0.11 at 0.99" the owner saw.
- `_paper_monitor_snapshot_row` (`strategy_research.py:2118-2122`) maps `live_bid → exit_price` (0.99) and `unrealized_pnl → realized_pnl`, so an **unrealized HOLD mark is displayed indistinguishably from a real close**.

**Fix:**
1. **Dedup per order** — `strategy_research.py:959-967`: `SELECT … FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY created_at DESC) rn FROM paper_monitor_snapshots) WHERE rn=1 ORDER BY created_at DESC LIMIT 12`, or dedup by id in the Python merge before truncating. Drops 8 → 3.
2. **Mark HOLD rows as "monitor inspection (unrealized)"** in `actionTable` (`strategy-lab.html:2565`) and label the P&L column unrealized for `status=HOLD`.

> *Note: bullet (b) in the original write-up said "14 NO rows"; the rendered array is **16 NO of 19** — immaterial to the conclusion.*

---

## 7. Prioritized Change List

Ordered by **ROI-per-risk** (highest first). **SAFE** = UI/diagnostic, no economic effect. **RISKY** = touches live sizing/gates.

| # | Change | File:line | Current → Proposed | Expected impact | Risk | Citation |
|---|---|---|---|---|---|---|
| 1 | Dedup `recent_monitor_actions` per order | `strategy_research.py:959-967` / `:1067-1083` | no GROUP BY → window-dedup by `order_id` | 8 duplicate HOLD lines → 3 distinct positions | **SAFE** | — |
| 2 | Relabel "+35%" badge as a forward rule, not a result | `strategy-lab.html:2469,2484` | "Take profit bid / +35.0% ROI" → "Take-profit target (rule)" | Removes false "every trade made +35%" impression | **SAFE** | — |
| 3 | Mark HOLD marks as unrealized | `strategy-lab.html:2565`; `strategy_research.py:2118-2122` | realized fields reused for live marks → explicit "unrealized" | Stops live marks reading as closes | **SAFE** | — |
| 4 | Filter settled/stale candidates before eval | candidate gen (`strategy_research.py`/`cli.py`) | feed past-date `ask≥0.999` markets → exclude | Denominator 24 → ~16; honest approval rate | **SAFE** (diagnostic) | — |
| 5 | Cap effective TP at reachable ceiling / absolute-cents rule | `strategy_research.py:1816-1822,1923` | `c·(1+T)` → `min(c·(1+T), 0.98−ε)` | Exit reads as designed; **PnL ≈ unchanged** | **SAFE** | Kaminski-Lo 2014 |
| 6 | Loosen `min_edge_lcb` (research profile only) | `config.py:174-204` (FAST_FEEDBACK) | −0.03 → **−0.07** | Approval **0% → 8%** (2 positive-EV trades, ~$2 max each) | **RISKY (low)** | Ottaviani-Sørensen 2010 |
| 7 | Raise `max_position_risk_pct` (balanced only, post-walk-forward) | `config.py:140-142` | 0.005 → **0.02–0.03** + scale event/exposure/contracts | Balanced realized **+$0.27 → +$1.08–1.62**; P(50% DD) <0.1% | **RISKY** | Kelly 1956; Thorp 2006; MTZ 2010 |
| 8 | Size against live bankroll (compounding) | `config.py:53` (`size_against_live_equity=False`) | False → **True** (after #7) | Enables exponential growth; required by Kelly | **RISKY** | Kelly 1956 |

---

## 8. What NOT to Change (and Why)

1. **Do NOT raise `fractional_kelly` as the primary fix.** It is **inert** while the dollar cap binds (Finding 1). Raising it does nothing until `max_position_risk_pct` is raised first. The cap is the lever.

2. **Do NOT touch the live (balanced/conservative) `min_edge_lcb ≥ 0` floor.** It is the proven defense against the documented 3/190 negative-LCB failure (`config.py:117-123`). The LCB gate sits *upstream* of sizing — keeping it intact is what guarantees that raising the dollar cap only scales **already-approved positive-edge** trades, never negative-edge ones. Loosen LCB **only** in the paper-only research profile.

3. **Do NOT loosen `min_edge` (point-edge ≥ 0.005).** That would admit zero/negative point-edge bets — the LCB change deliberately admits *only* positive point-edge trades.

4. **Do NOT loosen `max_model_market_gap` or the cheap-tail floors.** The `+0.23/+0.31` "edge" on the 1–4¢ tails (#8/#10/#12) is illusory — a 0.26–0.32 model-vs-market gap on a tiny tail is exactly the overconfidence the realized **1.9%-vs-8.7%** calibration miss already burned. Mean-estimation error dominates (20:2:1, Chopra-Ziemba via MTZ).

5. **Do NOT leverage on the +15.6% balanced ROI yet.** It rests on **2 resolved trades** — pure noise until a **walk-forward, after-fee backtest** confirms it. Gate every sizing increase behind that validation, and **never apply it to the negative-ROI fast-feedback profile**, which would only scale a loss.

6. **Do NOT expect the exit-model fix to add PnL.** Settled favorites already capture the full `(1−c)` at $1.00 — the maximum possible outcome. The take-profit rework is cosmetic. The genuine PnL levers are sizing (Finding 1) and frequency (Finding 4), both gated on validation.

7. **Do NOT exceed full Kelly, ever.** `g(2f*) ≈ 0` — overbetting throws away 100% of growth and is the asymmetric path to ruin (MTZ; the LTCM cautionary case). Target effective `k` in the 0.05–0.10 band, well below half-Kelly, until the edge is proven real.

**Citations:** Kelly (1956) — https://www.princeton.edu/~wbialek/rome/refs/kelly_56.pdf · Thorp (2006) — https://gwern.net/doc/statistics/decision/2006-thorp.pdf · MacLean, Thorp & Ziemba (2010), "Good and Bad Properties of the Kelly Criterion" — https://www.stat.berkeley.edu/~aldous/157/Papers/Good_Bad_Kelly.pdf · Kaminski & Lo (2014), *J. Financial Markets* 18:234–254 — https://dspace.mit.edu/handle/1721.1/114876 · Wolfers & Zitzewitz (2004), *JEP* 18(2) — https://www.nber.org/papers/w10504 · Snowberg & Wolfers (2010), *JPE* 118(4) — https://www.nber.org/system/files/working_papers/w15923/w15923.pdf · Ottaviani & Sørensen (2010), *AEJ: Micro* 2(1) — https://web.econ.ku.dk/sorensen/papers/niaflb.pdf
