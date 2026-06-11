from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import SERIES_TICKER
from .models import EventSnapshot, MarketBin, target_date_from_event_ticker


PROD_BASE_URL = "https://external-api.kalshi.com/trade-api/v2"
DEMO_BASE_URL = "https://demo-api.kalshi.co/trade-api/v2"


class KalshiPublicClient:
    """Tiny public Kalshi API client.

    The live-order API is intentionally absent from this class. Paper trading
    should remain unable to place real orders by construction.
    """

    def __init__(self, base_url: str = PROD_BASE_URL, timeout: int = 20) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = f"?{urlencode(params)}" if params else ""
        url = f"{self.base_url}/{path.lstrip('/')}{query}"
        request = Request(url, headers={"accept": "application/json"})
        with urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def get_series(self, series_ticker: str = SERIES_TICKER) -> dict[str, Any]:
        return self.get_json(f"series/{series_ticker}")

    def get_event(self, event_ticker: str, *, with_nested_markets: bool = True) -> EventSnapshot:
        payload = self.get_json(
            f"events/{event_ticker}",
            {"with_nested_markets": str(with_nested_markets).lower()},
        )
        return EventSnapshot.from_kalshi(payload["event"])

    def get_market(self, market_ticker: str) -> MarketBin:
        payload = self.get_json(f"markets/{market_ticker}")
        return MarketBin.from_kalshi(payload["market"])

    def list_events(
        self,
        *,
        series_ticker: str = SERIES_TICKER,
        limit: int = 50,
        cursor: str | None = None,
        with_nested_markets: bool = True,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "series_ticker": series_ticker,
            "limit": limit,
            "with_nested_markets": str(with_nested_markets).lower(),
        }
        if cursor:
            params["cursor"] = cursor
        return self.get_json("events", params)

    def list_event_snapshots(
        self,
        *,
        series_ticker: str = SERIES_TICKER,
        limit: int = 50,
        cursor: str | None = None,
        with_nested_markets: bool = True,
    ) -> list[EventSnapshot]:
        payload = self.list_events(
            series_ticker=series_ticker,
            limit=limit,
            cursor=cursor,
            with_nested_markets=with_nested_markets,
        )
        return [EventSnapshot.from_kalshi(row) for row in payload.get("events", [])]

    def find_event_by_date(
        self,
        target_date: date,
        *,
        series_ticker: str = SERIES_TICKER,
        max_pages: int = 4,
    ) -> EventSnapshot | None:
        expected = f"{series_ticker}-{target_date.strftime('%y%b%d').upper()}"
        cursor = None
        for _ in range(max_pages):
            payload = self.list_events(series_ticker=series_ticker, cursor=cursor)
            for event_payload in payload.get("events", []):
                if event_payload.get("event_ticker") == expected:
                    return EventSnapshot.from_kalshi(event_payload)
            cursor = payload.get("cursor")
            if not cursor:
                break
        return None

    def get_orderbook(self, market_ticker: str, depth: int = 10) -> dict[str, Any]:
        return self.get_json(f"markets/{market_ticker}/orderbook", {"depth": depth})

    def list_historical_markets(
        self,
        *,
        series_ticker: str = SERIES_TICKER,
        limit: int = 1000,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "series_ticker": series_ticker,
            "limit": limit,
        }
        if cursor:
            params["cursor"] = cursor
        return self.get_json("historical/markets", params)

    def get_historical_market_candlesticks(
        self,
        market_ticker: str,
        *,
        start_ts: int,
        end_ts: int,
        period_interval: int = 60,
    ) -> dict[str, Any]:
        return self.get_json(
            f"historical/markets/{market_ticker}/candlesticks",
            {
                "start_ts": start_ts,
                "end_ts": end_ts,
                "period_interval": period_interval,
            },
        )

    def get_historical_trades(
        self,
        *,
        ticker: str,
        min_ts: int,
        max_ts: int,
        limit: int = 1000,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "ticker": ticker,
            "min_ts": min_ts,
            "max_ts": max_ts,
            "limit": limit,
        }
        if cursor:
            params["cursor"] = cursor
        return self.get_json("historical/trades", params)


def load_event_snapshots(path: Path, target_date: date | None = None) -> list[EventSnapshot]:
    """Load Kalshi event JSON saved from either event or events endpoints."""

    payload = json.loads(path.read_text())
    if "event" in payload:
        events = [EventSnapshot.from_kalshi(payload["event"])]
    elif "events" in payload:
        events = [EventSnapshot.from_kalshi(row) for row in payload.get("events", [])]
    elif "markets" in payload:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for market in payload.get("markets", []):
            grouped.setdefault(market["event_ticker"], []).append(market)
        events = [
            EventSnapshot.from_kalshi(
                {
                    "event_ticker": event_ticker,
                    "title": f"Kalshi market snapshot {event_ticker}",
                    "markets": markets,
                }
            )
            for event_ticker, markets in grouped.items()
        ]
    elif "event_ticker" in payload:
        events = [EventSnapshot.from_kalshi(payload)]
    else:
        raise ValueError(f"Unrecognized Kalshi event payload: {path}")
    if target_date is not None:
        events = [event for event in events if event.target_date == target_date]
    return events
