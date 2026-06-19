"""DB-level backstop for the concurrent-open guard.

The application guard (has_active_paper_entry) is a check-then-insert across
separate SQLite connections, so a transient profile-normalization gap during a
deploy (the 2026-06-18 duplicate-open incident) or a check-then-insert race can
still slip a second OPEN order onto the same market/side/profile. A partial
UNIQUE index makes that physically impossible, while leaving arbitrage YES+NO
boxes and post-close re-entry untouched. record_paper_order translates the
constraint violation into a None return so the scan skips gracefully.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from sfo_kalshi_quant.db import PaperStore
from sfo_kalshi_quant.models import TradeDecision


def _decision(
    ticker: str = "KXHIGHTSFO-26JUN19-B72.5",
    *,
    side: str = "NO",
) -> TradeDecision:
    action = "BUY_NO" if side.upper() == "NO" else "BUY_YES"
    return TradeDecision(
        ticker=ticker,
        label="72° to 73°",
        action=action,
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
        recommended_contracts=3.0,
        expected_profit=0.5,
        reasons=[],
        trade_quality_score=80.0,
        side=side,
        strike_type="between",
        floor_strike=72.0,
        cap_strike=73.0,
    )


def _open_count(store: PaperStore, ticker: str, side: str, profile: str) -> int:
    with store.connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) FROM paper_orders
            WHERE target_date = ? AND market_ticker = ?
              AND UPPER(COALESCE(side, 'YES')) = ?
              AND COALESCE(risk_profile, 'live') = ?
              AND status IN ('PAPER_FILLED', 'PAPER_LIMIT_RESTING')
              AND settled_at IS NULL AND closed_at IS NULL
            """,
            ("2026-06-19", ticker, side.upper(), profile),
        ).fetchone()
    return int(row[0])


def test_guard_index_is_created_on_init():
    with TemporaryDirectory() as tmp:
        store = PaperStore(Path(tmp) / "paper.db")
        with store.connect() as conn:
            names = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index'"
                ).fetchall()
            }
        assert "ux_paper_orders_open_market_side_profile" in names


def test_duplicate_open_same_market_side_profile_is_rejected():
    with TemporaryDirectory() as tmp:
        store = PaperStore(Path(tmp) / "paper.db")
        first = store.record_paper_order("2026-06-19", _decision(), risk_profile="research")
        second = store.record_paper_order("2026-06-19", _decision(), risk_profile="research")

        assert isinstance(first, int)
        # The backstop rejects the concurrent duplicate; the store signals None.
        assert second is None
        assert _open_count(store, "KXHIGHTSFO-26JUN19-B72.5", "NO", "research") == 1


def test_same_market_other_profile_is_independent():
    # live and research are separate books; one open per book is fine.
    with TemporaryDirectory() as tmp:
        store = PaperStore(Path(tmp) / "paper.db")
        research = store.record_paper_order("2026-06-19", _decision(), risk_profile="research")
        live = store.record_paper_order("2026-06-19", _decision(), risk_profile="live")

        assert isinstance(research, int)
        assert isinstance(live, int)
        assert _open_count(store, "KXHIGHTSFO-26JUN19-B72.5", "NO", "research") == 1
        assert _open_count(store, "KXHIGHTSFO-26JUN19-B72.5", "NO", "live") == 1


def test_arbitrage_yes_and_no_box_on_one_market_is_allowed():
    # The index is side-inclusive precisely so a deliberate YES+NO box stays legal.
    with TemporaryDirectory() as tmp:
        store = PaperStore(Path(tmp) / "paper.db")
        no_leg = store.record_paper_order(
            "2026-06-19", _decision(side="NO"), risk_profile="research", group_id="ARB-test"
        )
        yes_leg = store.record_paper_order(
            "2026-06-19", _decision(side="YES"), risk_profile="research", group_id="ARB-test"
        )

        assert isinstance(no_leg, int)
        assert isinstance(yes_leg, int)
        assert _open_count(store, "KXHIGHTSFO-26JUN19-B72.5", "NO", "research") == 1
        assert _open_count(store, "KXHIGHTSFO-26JUN19-B72.5", "YES", "research") == 1


def test_reentry_after_close_is_allowed():
    # The index is partial on the open lifecycle, so re-entry after a close works.
    with TemporaryDirectory() as tmp:
        store = PaperStore(Path(tmp) / "paper.db")
        first = store.record_paper_order("2026-06-19", _decision(), risk_profile="research")
        store.close_paper_order(first, 0.5)
        second = store.record_paper_order("2026-06-19", _decision(), risk_profile="research")

        assert isinstance(first, int)
        assert isinstance(second, int)
        assert _open_count(store, "KXHIGHTSFO-26JUN19-B72.5", "NO", "research") == 1
