from __future__ import annotations

from dataclasses import replace

from sfo_kalshi_quant.config import StrategyConfig, strategy_config_for_profile
from sfo_kalshi_quant.models import BucketProbability, MarketBin
from sfo_kalshi_quant.risk import TradeEvaluator
from sfo_kalshi_quant.tail_basket import build_tail_basket


def _market(
    label: str,
    *,
    ticker: str,
    strike_type: str,
    floor: float | None = None,
    cap: float | None = None,
    yes_bid: float,
    yes_ask: float,
    no_bid: float,
    no_ask: float,
) -> MarketBin:
    return MarketBin(
        ticker=ticker,
        event_ticker="KXHIGHTSFO-26JUN11",
        title=f"SFO high {label}",
        yes_sub_title=label,
        strike_type=strike_type,
        floor_strike=floor,
        cap_strike=cap,
        yes_bid=yes_bid,
        yes_ask=yes_ask,
        no_bid=no_bid,
        no_ask=no_ask,
        yes_bid_size=200.0,
        yes_ask_size=200.0,
        status="active",
    )


def _screenshot_ladder() -> list[MarketBin]:
    return [
        _market(
            "81° or below",
            ticker="KXHIGHTSFO-26JUN11-T82",
            strike_type="less",
            cap=82,
            yes_bid=0.10,
            yes_ask=0.12,
            no_bid=0.88,
            no_ask=0.90,
        ),
        _market(
            "82° to 83°",
            ticker="KXHIGHTSFO-26JUN11-B82.5",
            strike_type="between",
            floor=82,
            cap=83,
            yes_bid=0.23,
            yes_ask=0.25,
            no_bid=0.74,
            no_ask=0.76,
        ),
        _market(
            "84° to 85°",
            ticker="KXHIGHTSFO-26JUN11-B84.5",
            strike_type="between",
            floor=84,
            cap=85,
            yes_bid=0.30,
            yes_ask=0.31,
            no_bid=0.68,
            no_ask=0.70,
        ),
        _market(
            "86° to 87°",
            ticker="KXHIGHTSFO-26JUN11-B86.5",
            strike_type="between",
            floor=86,
            cap=87,
            yes_bid=0.17,
            yes_ask=0.18,
            no_bid=0.81,
            no_ask=0.83,
        ),
        _market(
            "88° to 89°",
            ticker="KXHIGHTSFO-26JUN11-B88.5",
            strike_type="between",
            floor=88,
            cap=89,
            yes_bid=0.10,
            yes_ask=0.12,
            no_bid=0.87,
            no_ask=0.89,
        ),
        _market(
            "90° or above",
            ticker="KXHIGHTSFO-26JUN11-T89",
            strike_type="greater",
            floor=89,
            yes_bid=0.11,
            yes_ask=0.13,
            no_bid=0.86,
            no_ask=0.88,
        ),
    ]


def _probabilities(markets: list[MarketBin]) -> dict[str, BucketProbability]:
    by_label = {
        "81° or below": (0.04, 0.02, 0.05, 0.10),
        "82° to 83°": (0.18, 0.12, 0.18, 0.24),
        "84° to 85°": (0.40, 0.35, 0.40, 0.31),
        "86° to 87°": (0.22, 0.17, 0.22, 0.18),
        "88° to 89°": (0.15, 0.10, 0.15, 0.11),
        "90° or above": (0.03, 0.015, 0.03, 0.12),
    }
    results = {}
    for market in markets:
        probability, lower, model, market_p = by_label[market.yes_sub_title]
        results[market.ticker] = BucketProbability(
            ticker=market.ticker,
            label=market.yes_sub_title,
            probability=probability,
            lower_confidence=lower,
            empirical_probability=probability,
            normal_probability=probability,
            effective_n=250,
            residual_probability=probability,
            ensemble_probability=probability,
            model_probability=model,
            market_probability=market_p,
        )
    return results


def _config() -> StrategyConfig:
    return StrategyConfig(
        min_edge=0.0,
        min_edge_lcb=0.0,
        max_model_market_gap=0.25,
        max_spread=0.08,
        min_yes_bid_size=1.0,
        max_position_risk_pct=0.25,
        max_event_risk_pct=0.50,
        max_contracts_per_market=100.0,
    )


def test_tail_basket_selects_edge_no_legs_and_small_center_yes() -> None:
    markets = _screenshot_ladder()
    basket = build_tail_basket(
        markets,
        _probabilities(markets),
        predicted_high_f=85.0,
        evaluator=TradeEvaluator(_config()),
        bankroll=1000.0,
        tail_distance_f=3.0,
        tail_stake=5.0,
        center_stake=1.0,
        max_tail_yes_probability=0.12,
        max_basket_spend=12.0,
        max_worst_case_loss=8.0,
    )

    assert basket.approved, basket.reasons
    assert basket.center_label == "84° to 85°"
    assert basket.tail_yes_probability == 0.07
    assert [leg.kind for leg in basket.legs] == ["TAIL_NO", "TAIL_NO", "CENTER_YES"]
    assert [leg.decision.label for leg in basket.legs] == [
        "81° or below",
        "90° or above",
        "84° to 85°",
    ]
    assert all(leg.decision.approved for leg in basket.legs)
    tail_spend = sum(leg.spend for leg in basket.legs if leg.kind == "TAIL_NO")
    center_spend = sum(leg.spend for leg in basket.legs if leg.kind == "CENTER_YES")
    assert 0.0 < center_spend < tail_spend
    assert basket.worst_case_loss <= 8.0
    assert basket.total_spend <= 12.0


def test_tail_basket_rejects_when_tail_probability_is_too_large() -> None:
    markets = _screenshot_ladder()
    probabilities = _probabilities(markets)
    probabilities[markets[0].ticker] = replace(
        probabilities[markets[0].ticker],
        probability=0.20,
        lower_confidence=0.16,
        model_probability=0.20,
        market_probability=0.20,
    )

    basket = build_tail_basket(
        markets,
        probabilities,
        predicted_high_f=85.0,
        evaluator=TradeEvaluator(_config()),
        bankroll=1000.0,
        tail_distance_f=3.0,
        tail_stake=5.0,
        center_stake=1.0,
        max_tail_yes_probability=0.12,
        max_basket_spend=12.0,
        max_worst_case_loss=8.0,
    )

    assert not basket.approved
    assert any("tail probability" in reason for reason in basket.reasons)


def test_tail_basket_rejects_when_worst_case_loss_exceeds_guardrail() -> None:
    markets = _screenshot_ladder()
    basket = build_tail_basket(
        markets,
        _probabilities(markets),
        predicted_high_f=85.0,
        evaluator=TradeEvaluator(_config()),
        bankroll=1000.0,
        tail_distance_f=3.0,
        tail_stake=5.0,
        center_stake=1.0,
        max_tail_yes_probability=0.12,
        max_basket_spend=12.0,
        max_worst_case_loss=3.0,
    )

    assert not basket.approved
    assert any("worst-case loss" in reason for reason in basket.reasons)


def test_tail_basket_regime_block_binds_under_live_on_hot_day() -> None:
    # The live profile blocks the warm/hot regime. Now that build_tail_basket
    # threads forecast_high_f into the evaluator, a hot-day basket (forecast 85F)
    # places NO approved legs -- previously the regime block silently no-opped
    # because forecast_high_f was never forwarded to evaluate_market.
    markets = _screenshot_ladder()
    basket = build_tail_basket(
        markets,
        _probabilities(markets),
        predicted_high_f=85.0,  # HOT cohort -> blocked on live
        evaluator=TradeEvaluator(strategy_config_for_profile("live")),
        bankroll=1000.0,
        tail_distance_f=3.0,
        tail_stake=5.0,
        center_stake=1.0,
        max_tail_yes_probability=0.12,
        max_basket_spend=12.0,
        max_worst_case_loss=8.0,
    )
    assert not basket.approved
    assert all(not leg.decision.approved for leg in basket.legs)
    assert any(
        "regime" in reason
        for leg in basket.legs
        for reason in leg.decision.reasons
    )


def test_basket_kelly_sizing_deploys_more_than_fixed_stake() -> None:
    # tail_stake=None (the CLI's --basket-sizing kelly) lets each leg keep the
    # evaluator's risk-budget size instead of a hardcoded $5, so the basket
    # deploys materially more capital -- the fix for the inert "$1-2" P&L.
    markets = _screenshot_ladder()
    probs = _probabilities(markets)
    evaluator = TradeEvaluator(_config())
    common = dict(
        predicted_high_f=85.0,
        evaluator=evaluator,
        bankroll=200.0,
        tail_distance_f=3.0,
        center_stake=1.0,
        max_tail_yes_probability=0.12,
        max_basket_spend=200.0,
        max_worst_case_loss=200.0,
    )
    fixed = build_tail_basket(markets, probs, tail_stake=5.0, **common)
    kelly = build_tail_basket(markets, probs, tail_stake=None, **common)

    fixed_tail = sum(leg.spend for leg in fixed.legs if leg.kind == "TAIL_NO")
    kelly_tail = sum(leg.spend for leg in kelly.legs if leg.kind == "TAIL_NO")
    assert kelly_tail > fixed_tail
