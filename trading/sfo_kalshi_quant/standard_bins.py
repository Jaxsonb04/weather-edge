from __future__ import annotations

from .models import MarketBin


def standard_sfo_bins(event_ticker: str = "KXHIGHTSFO-PAPER") -> list[MarketBin]:
    """Fallback ladder matching the current SFO high-temperature market shape."""

    payloads = [
        {
            "ticker": f"{event_ticker}-T66",
            "event_ticker": event_ticker,
            "title": "Paper SFO high temperature <66",
            "yes_sub_title": "65° or below",
            "strike_type": "less",
            "cap_strike": 66,
        },
        {
            "ticker": f"{event_ticker}-B66.5",
            "event_ticker": event_ticker,
            "title": "Paper SFO high temperature 66-67",
            "yes_sub_title": "66° to 67°",
            "strike_type": "between",
            "floor_strike": 66,
            "cap_strike": 67,
        },
        {
            "ticker": f"{event_ticker}-B68.5",
            "event_ticker": event_ticker,
            "title": "Paper SFO high temperature 68-69",
            "yes_sub_title": "68° to 69°",
            "strike_type": "between",
            "floor_strike": 68,
            "cap_strike": 69,
        },
        {
            "ticker": f"{event_ticker}-B70.5",
            "event_ticker": event_ticker,
            "title": "Paper SFO high temperature 70-71",
            "yes_sub_title": "70° to 71°",
            "strike_type": "between",
            "floor_strike": 70,
            "cap_strike": 71,
        },
        {
            "ticker": f"{event_ticker}-B72.5",
            "event_ticker": event_ticker,
            "title": "Paper SFO high temperature 72-73",
            "yes_sub_title": "72° to 73°",
            "strike_type": "between",
            "floor_strike": 72,
            "cap_strike": 73,
        },
        {
            "ticker": f"{event_ticker}-T73",
            "event_ticker": event_ticker,
            "title": "Paper SFO high temperature >73",
            "yes_sub_title": "74° or above",
            "strike_type": "greater",
            "floor_strike": 73,
        },
    ]
    markets = []
    for payload in payloads:
        payload = {
            "yes_bid_dollars": "0.0000",
            "yes_ask_dollars": "1.0000",
            "no_bid_dollars": "0.0000",
            "no_ask_dollars": "1.0000",
            "yes_bid_size_fp": "0",
            "yes_ask_size_fp": "0",
            "status": "paper",
            **payload,
        }
        markets.append(MarketBin.from_kalshi(payload))
    return markets
