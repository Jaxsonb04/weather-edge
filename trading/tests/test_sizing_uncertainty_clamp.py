"""The sizing/LCB uncertainty clamp must neutralize degenerate certainty.

Intraday conditioning or a saturated normal-CDF can drive a side's probability
AND its lower-confidence bound to a literal 1.0. That nullifies the edge_lcb gate
(the primary defense against model overconfidence) and max-sizes Kelly off false
certainty -- the over-sizing behind the 22/16-contract NO favorites on 2026-06-18.
``min_probability_uncertainty`` caps the SIZING probability and the side LCB at
``1 - u`` so a near-certain favorite is gated and sized as the uncertain bet it
is, while leaving ordinary favorites (p ~0.85-0.93) untouched.
"""

from dataclasses import replace

from sfo_kalshi_quant.config import StrategyConfig
from sfo_kalshi_quant.models import BucketProbability, MarketBin
from sfo_kalshi_quant.risk import TradeEvaluator


def _permissive_config(uncertainty: float) -> StrategyConfig:
    """Baseline config with gates relaxed so only sizing differs, and the
    per-position cap lifted so Kelly (not the cap) is the binding constraint."""
    return replace(
        StrategyConfig(),
        min_probability_uncertainty=uncertainty,
        fractional_kelly=0.30,
        kelly_lcb_weight=0.5,
        max_position_risk_pct=0.9,
        max_event_risk_pct=0.9,
        max_target_exposure_pct=0.9,
        max_contracts_per_market=1_000_000.0,
        allow_fractional_contracts=True,
        min_edge=-1.0,
        min_edge_lcb=-1.0,
        max_spread=1.0,
        max_spread_fraction_of_cost=100.0,
        min_yes_bid=0.0,
        min_yes_bid_size=0.0,
        min_ask_size=0.0,
        max_model_market_gap=1.0,
        min_posterior_probability=0.0,
    )


def _no_favorite_market(no_ask: float = 0.92, no_bid: float = 0.90) -> MarketBin:
    # NO favorite; yes/no books are complementary (yes_bid = 1 - no_ask).
    return MarketBin(
        ticker="KXHIGHTSFO-TEST-B70.5",
        event_ticker="KXHIGHTSFO-TEST",
        title="Highest temperature in San Francisco?",
        yes_sub_title="70° to 71°",
        strike_type="between",
        floor_strike=70.0,
        cap_strike=71.0,
        yes_bid=round(1.0 - no_ask, 2),
        yes_ask=round(1.0 - no_bid, 2),
        no_bid=no_bid,
        no_ask=no_ask,
        # Deep book so the per-position Kelly budget (not the displayed ask size)
        # is the binding constraint -- the clamp acts on Kelly.
        yes_bid_size=1_000_000.0,
        yes_ask_size=1_000_000.0,
        status="active",
    )


def _bucket(probability: float, lower_confidence: float) -> BucketProbability:
    return BucketProbability(
        ticker="KXHIGHTSFO-TEST-B70.5",
        label="70° to 71°",
        probability=probability,
        lower_confidence=lower_confidence,
        empirical_probability=probability,
        normal_probability=probability,
        effective_n=200,
        model_probability=probability,
        market_probability=None,
    )


def test_degenerate_certainty_is_sized_down_by_the_clamp():
    """A degenerate NO favorite (YES p=0 -> NO p=1.0, NO LCB=1.0): with the clamp
    on it sizes strictly fewer contracts than with the clamp off."""
    market = _no_favorite_market()
    degenerate = _bucket(probability=0.0, lower_confidence=0.0)

    off = TradeEvaluator(_permissive_config(0.0)).evaluate_market(
        market, degenerate, bankroll=1000.0, side="NO"
    )
    on = TradeEvaluator(_permissive_config(0.04)).evaluate_market(
        market, degenerate, bankroll=1000.0, side="NO"
    )

    assert off.approved and on.approved
    assert on.recommended_contracts < off.recommended_contracts
    # The edge_lcb gate input is haircut too (no longer reads a free +0.08).
    assert on.edge_lcb < off.edge_lcb


def test_ordinary_favorite_is_untouched_by_the_clamp():
    """A normal favorite (NO p=0.94, NO LCB ~0.92) sits below the 1 - u ceiling,
    so the clamp must not change its sizing or its edge_lcb. Priced cheaper
    (cost ~0.79) so it carries a genuine edge and is approved."""
    market = _no_favorite_market(no_ask=0.78, no_bid=0.76)
    ordinary = _bucket(probability=0.06, lower_confidence=0.04)

    off = TradeEvaluator(_permissive_config(0.0)).evaluate_market(
        market, ordinary, bankroll=1000.0, side="NO"
    )
    on = TradeEvaluator(_permissive_config(0.04)).evaluate_market(
        market, ordinary, bankroll=1000.0, side="NO"
    )

    assert off.approved and on.approved
    assert abs(on.recommended_contracts - off.recommended_contracts) < 1e-9
    assert abs(on.edge_lcb - off.edge_lcb) < 1e-9


def test_clamp_is_a_noop_on_the_frozen_baseline():
    """The frozen StrategyConfig defaults min_probability_uncertainty to 0.0, so
    reproducible baseline behavior is preserved."""
    assert StrategyConfig().min_probability_uncertainty == 0.0
