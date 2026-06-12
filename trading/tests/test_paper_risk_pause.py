from pathlib import Path
from tempfile import TemporaryDirectory

from sfo_kalshi_quant.db import PaperStore
from sfo_kalshi_quant.models import TradeDecision
from sfo_kalshi_quant.paper import PaperTrader
from sfo_kalshi_quant.config import strategy_config_for_profile


def _decision(ticker: str = "KXHIGHTSFO-TEST-B70.5") -> TradeDecision:
    return TradeDecision(
        ticker=ticker,
        label="70° to 71°",
        action="BUY_YES",
        approved=True,
        probability=0.70,
        probability_lcb=0.62,
        yes_bid=0.48,
        yes_ask=0.50,
        spread=0.02,
        fee_per_contract=0.02,
        cost_per_contract=0.52,
        edge=0.18,
        edge_lcb=0.10,
        kelly_fraction=0.01,
        recommended_contracts=10.0,
        expected_profit=1.8,
        reasons=[],
        trade_quality_score=80.0,
        strike_type="between",
        floor_strike=70.0,
        cap_strike=71.0,
    )


def test_fast_feedback_pauses_after_five_bad_resolved_trades():
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "paper.db"
        store = PaperStore(db_path)
        for idx in range(5):
            order_id = store.record_paper_order(
                "2026-06-12",
                _decision(f"KXHIGHTSFO-TEST-B{70 + idx}.5"),
                risk_profile="fast-feedback",
            )
            store.close_paper_order(order_id, 0.01)

        reason = store.paper_entry_pause_reason(
            "fast-feedback",
            bankroll=1000.0,
            target_date="2026-06-13",
        )

        assert reason is not None
        assert "fast-feedback paused" in reason
        assert "resolved ROI" in reason
        trader = PaperTrader(
            store,
            strategy_config_for_profile("fast-feedback"),
            risk_profile="fast-feedback",
        )
        assert trader.place_approved("2026-06-13", [_decision()], bankroll=1000.0) == []


def test_balanced_does_not_pause_from_fast_feedback_losses():
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "paper.db"
        store = PaperStore(db_path)
        for idx in range(5):
            order_id = store.record_paper_order(
                "2026-06-12",
                _decision(f"KXHIGHTSFO-TEST-B{70 + idx}.5"),
                risk_profile="fast-feedback",
            )
            store.close_paper_order(order_id, 0.01)

        assert store.paper_entry_pause_reason(
            "balanced",
            bankroll=1000.0,
            target_date="2026-06-13",
        ) is None


def test_fast_feedback_pauses_after_daily_loss_limit():
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "paper.db"
        store = PaperStore(db_path)
        order_id = store.record_paper_order(
            "2026-06-12",
            _decision(),
            risk_profile="fast-feedback",
        )
        store.close_paper_order(order_id, 0.01)

        reason = store.paper_entry_pause_reason(
            "fast-feedback",
            bankroll=1000.0,
            target_date="2026-06-12",
        )

        assert reason is not None
        assert "daily loss" in reason
