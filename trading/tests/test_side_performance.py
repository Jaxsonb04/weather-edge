"""P1-E payload: YES-vs-NO performance split surfaced for the dashboard."""

from pathlib import Path
from tempfile import TemporaryDirectory

from sfo_kalshi_quant.config import StrategyConfig
from sfo_kalshi_quant.db import PaperStore
from sfo_kalshi_quant.models import TradeDecision
from sfo_kalshi_quant.summary import build_paper_summary


def _decision(ticker, action, side, *, cost, floor, cap):
    return TradeDecision(
        ticker=ticker,
        label=f"{floor:.0f}° to {cap:.0f}°",
        action=action,
        side=side,
        approved=True,
        probability=0.55,
        probability_lcb=0.45,
        yes_bid=0.30,
        yes_ask=0.33,
        spread=0.03,
        fee_per_contract=0.01,
        cost_per_contract=cost,
        edge=0.10,
        edge_lcb=0.03,
        kelly_fraction=0.01,
        recommended_contracts=10.0,
        expected_profit=1.0,
        reasons=[],
        entry_bid=0.30,
        entry_ask=0.33,
        strike_type="between",
        floor_strike=floor,
        cap_strike=cap,
    )


def test_side_performance_splits_yes_wins_from_no_losses():
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "paper.db"
        store = PaperStore(db_path)
        forecaster_root = Path(tmp) / "forecaster"
        forecaster_root.mkdir()

        # YES on 66-67 settles YES at high 67 -> a YES win.
        store.record_paper_order(
            "2026-06-03",
            _decision("KXHIGHTSFO-TEST-B66.5", "BUY_YES", "YES", cost=0.30, floor=66.0, cap=67.0),
        )
        store.settle_paper_orders("2026-06-03", 67)
        # NO on 66-67 also settles YES at high 67 -> a NO loss.
        store.record_paper_order(
            "2026-06-04",
            _decision("KXHIGHTSFO-TEST-B66.5", "BUY_NO", "NO", cost=0.30, floor=66.0, cap=67.0),
        )
        store.settle_paper_orders("2026-06-04", 67)

        payload = build_paper_summary(
            db_path=db_path,
            forecaster_root=forecaster_root,
            config=StrategyConfig(paper_bankroll=1000.0),
            days=30,
        )
        split = payload["side_performance"]
        assert split["YES"]["trades"] == 1
        assert split["YES"]["wins"] == 1
        assert split["YES"]["hit_rate"] == 1.0
        assert split["YES"]["realized_pnl"] > 0
        assert split["NO"]["trades"] == 1
        assert split["NO"]["losses"] == 1
        assert split["NO"]["hit_rate"] == 0.0
        assert split["NO"]["realized_pnl"] < 0
