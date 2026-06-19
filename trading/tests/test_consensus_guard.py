"""Market-consensus anchor + guard: heavier market weight in the blend and a
"don't bet hard against a confident, liquid market" size haircut. Opt-in;
default OFF on live, ON for research."""

import math
from dataclasses import replace

from sfo_kalshi_quant.config import StrategyConfig, strategy_config_for_profile
from sfo_kalshi_quant.consensus import build_market_consensus
from sfo_kalshi_quant.models import BucketProbability, MarketBin
from sfo_kalshi_quant.probability import _model_weight
from sfo_kalshi_quant.risk import TradeEvaluator, _consensus_guard_assessment


def _bin(label, strike_type, floor, cap, yes_bid, yes_ask, *, size=150):
    return MarketBin.from_kalshi(
        {
            "ticker": f"KXHIGHTSFO-26JUN20-{label}",
            "event_ticker": "KXHIGHTSFO-26JUN20",
            "title": "",
            "yes_sub_title": label,
            "strike_type": strike_type,
            "floor_strike": floor,
            "cap_strike": cap,
            "yes_bid_dollars": yes_bid,
            "yes_ask_dollars": yes_ask,
            "no_bid_dollars": round(1.0 - yes_ask, 2),
            "no_ask_dollars": round(1.0 - yes_bid, 2),
            "yes_bid_size_fp": size,
            "yes_ask_size_fp": size,
            "status": "active",
        }
    )


def _confident_ladder():
    return [
        _bin("B64", "between", 63, 64, 0.04, 0.06),
        _bin("B66", "between", 65, 66, 0.14, 0.16),
        _bin("B68", "between", 67, 68, 0.40, 0.43),
        _bin("B70", "between", 69, 70, 0.20, 0.23),
        _bin("B72", "between", 71, 72, 0.06, 0.08),
    ]


# --- config invariant: opt-in, default OFF on live, ON for research ---------

def test_anchor_and_guard_default_off_and_research_on():
    base = StrategyConfig()
    assert base.market_consensus_anchor_enabled is False
    assert base.market_consensus_guard_enabled is False

    live = strategy_config_for_profile("live")
    assert live.market_consensus_anchor_enabled is False
    assert live.market_consensus_guard_enabled is False

    research = strategy_config_for_profile("research")
    assert research.market_consensus_anchor_enabled is True
    assert research.market_consensus_guard_enabled is True


# --- anchor: heavier market voice in the blend ------------------------------

def test_anchor_lifts_market_weight_without_silencing_the_model():
    market = _confident_ladder()[2]  # tight, deep, consistent -> high reliability
    base = StrategyConfig()
    anchored = StrategyConfig(market_consensus_anchor_enabled=True)

    base_model_weight = _model_weight(0.0, market=market, config=base)
    anchored_model_weight = _model_weight(0.0, market=market, config=anchored)

    # The market gets a heavier voice (model weight drops) ...
    assert anchored_model_weight < base_model_weight
    # ... but the model is never silenced below its floor (edge stays alive).
    assert anchored_model_weight >= anchored.market_consensus_anchor_min_model_weight - 1e-9


# --- guard unit behavior ----------------------------------------------------

def test_guard_is_inert_when_disabled():
    consensus = build_market_consensus(_confident_ladder())
    base = StrategyConfig()  # guard disabled
    assert _consensus_guard_assessment(
        market_consensus=consensus, forecast_high_f=80.0, config=base
    ) == 1.0


def test_guard_is_inert_without_a_consensus_or_forecast():
    research = strategy_config_for_profile("research")
    consensus = build_market_consensus(_confident_ladder())
    assert _consensus_guard_assessment(
        market_consensus=None, forecast_high_f=80.0, config=research
    ) == 1.0
    assert _consensus_guard_assessment(
        market_consensus=build_market_consensus([]), forecast_high_f=80.0, config=research
    ) == 1.0
    assert _consensus_guard_assessment(
        market_consensus=consensus, forecast_high_f=None, config=research
    ) == 1.0


def test_guard_haircuts_a_confident_contrarian_disagreement():
    research = strategy_config_for_profile("research")
    consensus = build_market_consensus(_confident_ladder())
    # Forecast far above a tight, deep, well-formed market -> haircut.
    far = consensus.implied_high_f + research.market_consensus_guard_gap_f + 1.0
    multiplier = _consensus_guard_assessment(
        market_consensus=consensus, forecast_high_f=far, config=research
    )
    assert multiplier == research.market_consensus_guard_size_haircut


def test_guard_does_not_fire_on_small_disagreement():
    research = strategy_config_for_profile("research")
    consensus = build_market_consensus(_confident_ladder())
    near = consensus.implied_high_f + 0.5  # well inside the gap threshold
    assert _consensus_guard_assessment(
        market_consensus=consensus, forecast_high_f=near, config=research
    ) == 1.0


def test_guard_does_not_fire_when_market_is_uncertain():
    research = strategy_config_for_profile("research")
    consensus = build_market_consensus(_confident_ladder())
    far = consensus.implied_high_f + 10.0
    # Pretend the market's implied spread is very wide -> not a confident crowd.
    uncertain = replace(consensus, implied_stdev_f=research.market_consensus_guard_max_stdev_f + 5.0)
    assert _consensus_guard_assessment(
        market_consensus=uncertain, forecast_high_f=far, config=research
    ) == 1.0


def test_guard_does_not_fire_on_thin_or_inconsistent_book():
    research = strategy_config_for_profile("research")
    consensus = build_market_consensus(_confident_ladder())
    far = consensus.implied_high_f + 10.0
    thin = replace(consensus, liquid_bin_count=research.market_consensus_guard_min_bins - 1)
    assert _consensus_guard_assessment(
        market_consensus=thin, forecast_high_f=far, config=research
    ) == 1.0
    malformed = replace(consensus, overround=research.market_consensus_guard_max_overround + 0.5)
    assert _consensus_guard_assessment(
        market_consensus=malformed, forecast_high_f=far, config=research
    ) == 1.0
    # A deeply negative (incomplete) book is rejected too -- it is |overround|.
    incomplete = replace(consensus, overround=-(research.market_consensus_guard_max_overround + 0.5))
    assert _consensus_guard_assessment(
        market_consensus=incomplete, forecast_high_f=far, config=research
    ) == 1.0


# --- guard integration: shrinks size, never blocks --------------------------

def _approved_yes_setup():
    """A clearly-approved YES bet whose size is spend-budget bound."""

    market = _bin("B68", "between", 67, 68, 0.40, 0.42, size=400)
    probability = BucketProbability(
        ticker=market.ticker,
        label=market.yes_sub_title,
        probability=0.62,
        lower_confidence=0.58,
        empirical_probability=0.62,
        normal_probability=0.62,
        effective_n=400,
        model_probability=0.62,
        market_probability=0.60,
    )
    return market, probability


def test_guard_halves_size_but_keeps_the_trade_approved():
    consensus = build_market_consensus(_confident_ladder())
    far = consensus.implied_high_f + 8.0  # big confident disagreement
    market, probability = _approved_yes_setup()

    # Fractional contracts so the 0.5 haircut shows cleanly.
    guard_on = strategy_config_for_profile("research")
    guard_on = replace(
        guard_on,
        allow_fractional_contracts=True,
        # Neutralize the research regime block so a 75F-ish forecast still trades.
        blocked_forecast_cohorts=(),
        # Lift the per-market contract cap so the spend budget (which the guard
        # actually haircuts) is the binding lever in both runs, isolating the
        # exact 0.5 multiplier rather than a cap that masks it.
        max_contracts_per_market=10000.0,
    )
    guard_off = replace(guard_on, market_consensus_guard_enabled=False)

    plain = TradeEvaluator(guard_off).evaluate_market(
        market, probability, bankroll=1000.0, side="YES",
        forecast_high_f=far, market_consensus=consensus,
    )
    haircut = TradeEvaluator(guard_on).evaluate_market(
        market, probability, bankroll=1000.0, side="YES",
        forecast_high_f=far, market_consensus=consensus,
    )

    assert plain.approved is True
    assert haircut.approved is True  # the guard NEVER blocks a trade
    assert haircut.recommended_contracts > 0
    assert haircut.recommended_contracts < plain.recommended_contracts
    assert math.isclose(
        haircut.recommended_contracts,
        guard_on.market_consensus_guard_size_haircut * plain.recommended_contracts,
        rel_tol=1e-3,
    )
