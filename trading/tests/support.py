"""Shared test helpers for the paper-trading suite."""

from __future__ import annotations

from collections.abc import Iterable

from sfo_kalshi_quant.models import EventSnapshot, MarketBin, TradeDecision

# A close time far in the future so a wall-clock `created_at` is provably before
# it. Used to mark recorded decisions as legitimately pre-resolution.
FAR_FUTURE_CLOSE = "2099-01-01T00:00:00Z"


def pre_resolution_event(
    decisions: Iterable[TradeDecision],
    *,
    close_time: str = FAR_FUTURE_CLOSE,
    event_ticker: str = "KXHIGHTSFO-TEST",
) -> EventSnapshot:
    """An ``EventSnapshot`` whose markets carry a future ``close_time``.

    ``record_decisions`` stores ``market_close_time = NULL`` when no ``event=``
    is passed, and ``_is_pre_resolution_decision`` (correctly) treats a row it
    cannot prove predates market close as post-resolution — so a fixture that
    records a past-dated decision at wall-clock ``now`` is dropped from the
    signal backtest. Threading this event restores the intended pre-resolution
    behaviour while exercising the real ``event.markets -> market.raw ->
    close_time`` path that production uses.
    """

    markets = [
        MarketBin(
            ticker=decision.ticker,
            event_ticker=event_ticker,
            title="",
            yes_sub_title=decision.label,
            strike_type=decision.strike_type or "",
            floor_strike=decision.floor_strike,
            cap_strike=decision.cap_strike,
            yes_bid=decision.yes_bid,
            yes_ask=decision.yes_ask,
            no_bid=0.0,
            no_ask=0.0,
            yes_bid_size=0.0,
            yes_ask_size=0.0,
            status="active",
            raw={"close_time": close_time},
        )
        for decision in decisions
    ]
    return EventSnapshot(
        event_ticker=event_ticker,
        title="",
        target_date=None,
        markets=markets,
        raw={},
    )
