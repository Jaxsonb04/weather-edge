"""The paper monitor's stop-loss veto must only trust fresh model snapshots."""

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from sfo_kalshi_quant.db import PaperStore
from sfo_kalshi_quant.models import BucketProbability


def _probability(ticker: str, probability: float) -> BucketProbability:
    return BucketProbability(
        ticker=ticker,
        label="77° to 78°",
        probability=probability,
        lower_confidence=probability - 0.1,
        empirical_probability=probability,
        normal_probability=probability,
        effective_n=200,
    )


def test_latest_model_probability_returns_fresh_snapshot():
    with TemporaryDirectory() as tmp:
        store = PaperStore(Path(tmp) / "paper.db")
        store.record_probabilities(
            "2026-06-10", [_probability("KXHIGHTSFO-TEST-B77.5", 0.62)]
        )
        value = store.latest_model_probability("2026-06-10", "KXHIGHTSFO-TEST-B77.5")
        assert value is not None
        assert abs(value - 0.62) < 1e-9


def test_latest_model_probability_ignores_stale_snapshot():
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "paper.db"
        store = PaperStore(db_path)
        store.record_probabilities(
            "2026-06-10", [_probability("KXHIGHTSFO-TEST-B77.5", 0.62)]
        )
        stale = (datetime.now(UTC) - timedelta(hours=3)).isoformat()
        with sqlite3.connect(db_path) as conn:
            conn.execute("UPDATE probability_snapshots SET created_at = ?", (stale,))
        assert store.latest_model_probability("2026-06-10", "KXHIGHTSFO-TEST-B77.5") is None


def test_latest_model_probability_missing_market_is_none():
    with TemporaryDirectory() as tmp:
        store = PaperStore(Path(tmp) / "paper.db")
        assert store.latest_model_probability("2026-06-10", "KXHIGHTSFO-TEST-T78") is None
