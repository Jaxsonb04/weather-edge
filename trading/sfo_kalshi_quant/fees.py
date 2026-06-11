from __future__ import annotations

import math


def ceil_to_cent(value: float) -> float:
    """Round fees up to the next cent.

    Kalshi's fee schedule rounds exchange fees to cents. For strategy testing we
    intentionally round conservatively so edge is not overstated.
    """

    if value <= 0:
        return 0.0
    return math.ceil((value * 100.0) - 1e-12) / 100.0


def quadratic_fee_total(
    price: float,
    contracts: float = 1.0,
    *,
    maker: bool = False,
    fee_multiplier: float = 1.0,
    taker_rate: float = 0.07,
    maker_rate: float = 0.0175,
) -> float:
    """Estimate total Kalshi fee for binary weather contracts.

    Prices are represented in dollars from 0.00 to 1.00. The quadratic fee is
    largest near 50c and shrinks near 0c/100c.
    """

    if price <= 0 or price >= 1 or contracts <= 0:
        return 0.0
    rate = maker_rate if maker else taker_rate
    return ceil_to_cent(rate * fee_multiplier * contracts * price * (1.0 - price))


def quadratic_fee_per_contract(
    price: float,
    *,
    maker: bool = False,
    fee_multiplier: float = 1.0,
    taker_rate: float = 0.07,
    maker_rate: float = 0.0175,
) -> float:
    return quadratic_fee_total(
        price,
        1.0,
        maker=maker,
        fee_multiplier=fee_multiplier,
        taker_rate=taker_rate,
        maker_rate=maker_rate,
    )


def quadratic_fee_average_per_contract(
    price: float,
    contracts: float,
    *,
    maker: bool = False,
    fee_multiplier: float = 1.0,
    taker_rate: float = 0.07,
    maker_rate: float = 0.0175,
) -> float:
    if contracts <= 0:
        return 0.0
    return quadratic_fee_total(
        price,
        contracts,
        maker=maker,
        fee_multiplier=fee_multiplier,
        taker_rate=taker_rate,
        maker_rate=maker_rate,
    ) / contracts


def contracts_for_budget(price: float, budget: float) -> float:
    if price <= 0 or price >= 1 or budget <= 0:
        return 0.0
    lo = 0.0
    hi = budget / price
    for _ in range(48):
        mid = (lo + hi) / 2.0
        cost = price * mid + quadratic_fee_total(price, mid)
        if cost <= budget:
            lo = mid
        else:
            hi = mid
    return lo


def expected_profit_per_yes_contract(win_probability: float, ask_price: float, fee: float) -> float:
    """Expected dollar profit for buying one YES contract at ask."""

    return win_probability * (1.0 - ask_price) - (1.0 - win_probability) * ask_price - fee


def kelly_fraction_spent(win_probability: float, cost: float) -> float:
    """Kelly fraction of bankroll to spend on a binary contract.

    A YES contract costs ``cost`` and pays 1.00 if it resolves YES. The returned
    fraction is the Kelly fraction of bankroll allocated to the purchase cost.
    """

    if cost <= 0 or cost >= 1:
        return 0.0
    edge = win_probability - cost
    if edge <= 0:
        return 0.0
    return edge / (1.0 - cost)
