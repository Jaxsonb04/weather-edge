from datetime import date, timedelta

from sfo_kalshi_quant.backtest import run_walk_forward_calibration_backtest
from sfo_kalshi_quant.config import StrategyConfig
from sfo_kalshi_quant.models import ForecastOutcome


def test_walk_forward_backtest_returns_calibration_buckets():
    start = date(2025, 1, 1)
    outcomes = []
    for idx in range(80):
        pred = 66.0 + (idx % 8)
        actual = pred + [-2, -1, 0, 1, 2, 3, -1, 0][idx % 8]
        outcomes.append(
            ForecastOutcome(
                local_date=start + timedelta(days=idx),
                predicted_high_f=pred,
                actual_high_f=actual,
            )
        )

    result = run_walk_forward_calibration_backtest(
        outcomes,
        config=StrategyConfig(min_conditional_samples=10),
        min_train=40,
    )

    assert result.n == 40
    assert len(result.calibration_buckets) == 10
    assert sum(bucket.count for bucket in result.calibration_buckets) > result.n
    assert result.cohorts
    assert sum(cohort.count for cohort in result.cohorts) == result.n
