"""Kalshi market-implied consensus extraction: de-vig the bin ladder into a
coherent forecast (implied high, distribution, percentiles, confidence)."""

import math

from sfo_kalshi_quant.consensus import build_market_consensus
from sfo_kalshi_quant.models import MarketBin
from sfo_kalshi_quant.probability import (
    market_implied_probabilities,
    market_implied_yes_value,
)


def _bin(label, strike_type, floor, cap, yes_bid, yes_ask, *, size=150, two_sided=True, last=None):
    no_bid = round(1.0 - yes_ask, 2) if two_sided else 0.0
    no_ask = round(1.0 - yes_bid, 2) if two_sided else 1.0
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
            "no_bid_dollars": no_bid,
            "no_ask_dollars": no_ask,
            "yes_bid_size_fp": size,
            "yes_ask_size_fp": size,
            "last_price_dollars": last,
            "status": "active",
        }
    )


def _peaked_ladder():
    """A tight 2F-wide ladder peaking on the 67-68 bin."""

    return [
        _bin("T63", "less", 63, 63, 0.01, 0.03),
        _bin("B64", "between", 63, 64, 0.04, 0.06),
        _bin("B66", "between", 65, 66, 0.14, 0.16),
        _bin("B68", "between", 67, 68, 0.40, 0.43),
        _bin("B70", "between", 69, 70, 0.20, 0.23),
        _bin("B72", "between", 71, 72, 0.06, 0.08),
        _bin("G73", "greater", 73, 73, 0.01, 0.03),
    ]


def test_empty_ladder_is_unavailable():
    consensus = build_market_consensus([])
    assert consensus.available is False
    assert consensus.implied_high_f is None
    assert consensus.median_f is None
    # gap helper degrades gracefully when there is nothing to compare against.
    assert consensus.gap_to_forecast_f(70.0) is None


def test_no_book_ladder_is_unavailable():
    # Every bin one-sided with no real quote -> no implied distribution.
    flat = [_bin("B68", "between", 67, 68, 0.0, 1.0, two_sided=False)]
    consensus = build_market_consensus(flat)
    assert consensus.available is False


def test_peaked_ladder_distribution_is_coherent():
    consensus = build_market_consensus(_peaked_ladder())
    assert consensus.available is True

    # Mass de-vigs to a proper distribution.
    total = sum(b.implied_probability for b in consensus.bins)
    assert abs(total - 1.0) < 1e-9

    # The implied high lands in the body, just under the 67-68 modal bin.
    assert 67.0 <= consensus.implied_high_f <= 68.5
    assert consensus.modal_bin_label == "B68"
    assert consensus.modal_probability > 0.30

    # A tight ladder reads as a confident (small) implied spread.
    assert 0.0 < consensus.implied_stdev_f < 4.0

    # Percentiles are monotone and bracket the median.
    assert (
        consensus.p10_f
        < consensus.p25_f
        < consensus.median_f
        < consensus.p75_f
        < consensus.p90_f
    )
    assert abs(consensus.median_f - consensus.implied_high_f) < 2.0


def test_gap_to_forecast_is_signed_model_minus_market():
    consensus = build_market_consensus(_peaked_ladder())
    warm_gap = consensus.gap_to_forecast_f(consensus.implied_high_f + 3.0)
    cool_gap = consensus.gap_to_forecast_f(consensus.implied_high_f - 3.0)
    assert warm_gap > 0  # our model warmer than the market
    assert cool_gap < 0  # our model cooler than the market
    assert abs(warm_gap - 3.0) < 1e-6


def test_single_bin_is_a_degenerate_point():
    consensus = build_market_consensus([_bin("B68", "between", 67, 68, 0.40, 0.43)])
    assert consensus.available is True
    # One bin -> all mass there: zero spread, median at the bin center.
    assert consensus.implied_stdev_f == 0.0
    assert math.isclose(consensus.median_f, consensus.implied_high_f, abs_tol=0.6)
    assert consensus.modal_probability == 1.0


def test_open_tails_do_not_blow_up_the_mean():
    # A ladder with heavy open-tail bins must still produce a finite, sane mean
    # (tails are placed one bin-width inside the boundary, not at +/- infinity).
    ladder = [
        _bin("T60", "less", 60, 60, 0.30, 0.33),
        _bin("B62", "between", 61, 62, 0.30, 0.33),
        _bin("G63", "greater", 63, 63, 0.30, 0.33),
    ]
    consensus = build_market_consensus(ladder)
    assert consensus.available is True
    assert math.isfinite(consensus.implied_high_f)
    assert 55.0 < consensus.implied_high_f < 67.0


def test_two_sided_liquidity_is_counted():
    ladder = [
        _bin("B66", "between", 65, 66, 0.30, 0.33),  # two-sided
        _bin("B68", "between", 67, 68, 0.0, 1.0, two_sided=False),  # no book
    ]
    consensus = build_market_consensus(ladder)
    assert consensus.liquid_bin_count == 1


def test_forecast_tracks_last_trade_over_mid():
    # Kalshi volume-weights its headline forecast toward the last trade. Two bins
    # with identical bid/ask: mid-only weights them equally, but last trades that
    # favor the hotter bin must pull the reconstructed forecast hotter.
    mid_only = build_market_consensus(
        [
            _bin("B66", "between", 65, 66, 0.30, 0.34),
            _bin("B70", "between", 69, 70, 0.30, 0.34),
        ]
    )
    last_based = build_market_consensus(
        [
            _bin("B66", "between", 65, 66, 0.30, 0.34, last=0.10),
            _bin("B70", "between", 69, 70, 0.30, 0.34, last=0.80),
        ]
    )
    assert last_based.implied_high_f > mid_only.implied_high_f + 1.0
    # No last trade -> falls back to the bid/ask mid (so other tests are stable).
    no_trade = build_market_consensus([_bin("B68", "between", 67, 68, 0.40, 0.43)])
    assert no_trade.available is True


def test_public_devig_aliases_match_private_path():
    ladder = _peaked_ladder()
    probabilities = market_implied_probabilities(ladder)
    assert abs(sum(probabilities.values()) - 1.0) < 1e-9
    # Single-bin alias returns a value in (0, 1) for a real two-sided quote.
    value = market_implied_yes_value(ladder[3])
    assert value is not None and 0.0 < value < 1.0
