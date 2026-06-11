from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from .forecast import ForecastDataError, SfoForecasterAdapter
from .models import ForecastOutcome


DEFAULT_MIN_MATCHED_ROWS = 30
DEFAULT_MIN_MAE_IMPROVEMENT_F = 0.25
DEFAULT_HOLDOUT_FRACTION = 0.25
DEFAULT_MIN_AFTER_COST_TRADES = 30


@dataclass(frozen=True)
class _FeatureCandidate:
    source: str
    model: str
    variable: str
    lead_hours: float | None
    rows: tuple[tuple[date, float], ...]

    @property
    def key(self) -> str:
        lead = "none" if self.lead_hours is None else f"{self.lead_hours:g}h"
        return f"{self.source}/{self.model}/{self.variable}/{lead}"


def build_dataset_research(
    *,
    db_path: Path,
    forecaster_root: Path,
    min_matched_rows: int = DEFAULT_MIN_MATCHED_ROWS,
    min_mae_improvement_f: float = DEFAULT_MIN_MAE_IMPROVEMENT_F,
    holdout_fraction: float = DEFAULT_HOLDOUT_FRACTION,
    min_after_cost_trades: int = DEFAULT_MIN_AFTER_COST_TRADES,
) -> dict[str, Any]:
    """Evaluate whether collected external datasets are ready for model/trade use.

    This report is intentionally conservative. It can flag a dataset forecast
    feature as an accuracy candidate, but it keeps the overall status in
    collect-only mode until a separate after-cost trading test exists.
    """

    db_path = Path(db_path)
    generated_at = datetime.now(UTC).isoformat()
    try:
        baseline_outcomes = SfoForecasterAdapter(forecaster_root).load_lstm_outcomes()
    except (ForecastDataError, FileNotFoundError, KeyError, ValueError) as exc:
        return {
            "schema_version": 1,
            "generated_at": generated_at,
            "status": "collect_only",
            "available": False,
            "reason": f"baseline outcomes unavailable: {exc}",
            "accuracy_gate": {"available": False, "candidates": []},
            "profitability_gate": _profitability_gate({}, min_after_cost_trades=min_after_cost_trades),
        }

    baseline_by_date = {row.local_date: row for row in baseline_outcomes}
    candidates = _load_forecast_feature_candidates(db_path)
    accuracy_rows = [
        _candidate_payload(
            candidate,
            baseline_by_date=baseline_by_date,
            min_matched_rows=min_matched_rows,
            min_mae_improvement_f=min_mae_improvement_f,
            holdout_fraction=holdout_fraction,
        )
        for candidate in candidates
    ]
    accuracy_rows.sort(
        key=lambda row: (
            row["decision"] != "accuracy_candidate",
            row["holdout"].get("mae_delta_vs_baseline_f", math.inf),
            row["dataset_key"],
        )
    )
    market_counts = _market_history_counts(db_path)
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "status": "collect_only",
        "available": True,
        "baseline": {
            "source": "lstm",
            "outcome_count": len(baseline_outcomes),
            "settlement": "rounded SFO high temperature",
        },
        "accuracy_gate": {
            "available": True,
            "minimum_matched_rows": min_matched_rows,
            "minimum_holdout_mae_improvement_f": min_mae_improvement_f,
            "holdout_fraction": holdout_fraction,
            "candidate_count": len(accuracy_rows),
            "accuracy_candidate_count": sum(1 for row in accuracy_rows if row["decision"] == "accuracy_candidate"),
            "candidates": accuracy_rows,
        },
        "profitability_gate": _profitability_gate(
            market_counts,
            min_after_cost_trades=min_after_cost_trades,
        ),
        "promotion_rule": (
            "Collect broadly, but do not give a new source live model weight or "
            "loosen paper-trading gates until it improves held-out forecast error "
            "and then survives an after-cost market backtest with enough trades."
        ),
    }


def write_dataset_research(path: Path, payload: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_forecast_feature_candidates(db_path: Path) -> list[_FeatureCandidate]:
    if not Path(db_path).exists():
        return []
    query = """
        SELECT source, model, variable, lead_hours, target_date, value, issued_at
        FROM dataset_forecast_features
        WHERE value IS NOT NULL
          AND target_date IS NOT NULL
          AND variable LIKE '%temperature_2m_max%'
        ORDER BY source, model, variable, lead_hours, target_date, issued_at
    """
    try:
        with sqlite3.connect(db_path) as conn:
            if not _table_exists(conn, "dataset_forecast_features"):
                return []
            rows = conn.execute(query).fetchall()
    except sqlite3.Error:
        return []

    latest_by_key_day: dict[tuple[str, str, str, float | None, str], tuple[str, float]] = {}
    for source, model, variable, lead_hours, target_iso, value, issued_at in rows:
        key = (str(source), str(model), str(variable), _maybe_float(lead_hours), str(target_iso))
        current = latest_by_key_day.get(key)
        if current is None or str(issued_at) > current[0]:
            latest_by_key_day[key] = (str(issued_at), float(value))

    grouped: dict[tuple[str, str, str, float | None], list[tuple[date, float]]] = defaultdict(list)
    for (source, model, variable, lead_hours, target_iso), (_, value) in latest_by_key_day.items():
        grouped[(source, model, variable, lead_hours)].append((date.fromisoformat(target_iso), value))

    return [
        _FeatureCandidate(source, model, variable, lead_hours, tuple(sorted(values)))
        for (source, model, variable, lead_hours), values in grouped.items()
    ]


def _candidate_payload(
    candidate: _FeatureCandidate,
    *,
    baseline_by_date: dict[date, ForecastOutcome],
    min_matched_rows: int,
    min_mae_improvement_f: float,
    holdout_fraction: float,
) -> dict[str, Any]:
    matched = [
        (target, value, baseline_by_date[target])
        for target, value in candidate.rows
        if target in baseline_by_date
    ]
    n = len(matched)
    all_metrics = _metrics(matched)
    holdout = _holdout_metrics(matched, holdout_fraction=holdout_fraction)
    if n < min_matched_rows:
        decision = "collect_only"
        reason = f"needs at least {min_matched_rows} matched settlement rows; has {n}"
    elif holdout["mae_delta_vs_baseline_f"] <= -min_mae_improvement_f:
        decision = "accuracy_candidate"
        reason = "beats baseline on held-out matched dates"
    else:
        decision = "collect_only"
        reason = "does not beat baseline by the required held-out MAE margin"
    return {
        "dataset_key": candidate.key,
        "source": candidate.source,
        "model": candidate.model,
        "variable": candidate.variable,
        "lead_hours": candidate.lead_hours,
        "matched_rows": n,
        "decision": decision,
        "reason": reason,
        "all_matched": all_metrics,
        "holdout": holdout,
    }


def _metrics(rows: list[tuple[date, float, ForecastOutcome]]) -> dict[str, Any]:
    if not rows:
        return {
            "n": 0,
            "dataset_mae_f": None,
            "baseline_mae_f": None,
            "mae_delta_vs_baseline_f": None,
            "dataset_bias_f": None,
            "baseline_bias_f": None,
        }
    dataset_errors = [value - outcome.actual_high_f for _, value, outcome in rows]
    baseline_errors = [outcome.predicted_high_f - outcome.actual_high_f for _, _, outcome in rows]
    return {
        "n": len(rows),
        "dataset_mae_f": _round(_mae(dataset_errors)),
        "baseline_mae_f": _round(_mae(baseline_errors)),
        "mae_delta_vs_baseline_f": _round(_mae(dataset_errors) - _mae(baseline_errors)),
        "dataset_bias_f": _round(sum(dataset_errors) / len(dataset_errors)),
        "baseline_bias_f": _round(sum(baseline_errors) / len(baseline_errors)),
    }


def _holdout_metrics(
    rows: list[tuple[date, float, ForecastOutcome]],
    *,
    holdout_fraction: float,
) -> dict[str, Any]:
    if not rows:
        return _metrics([])
    holdout_fraction = min(0.9, max(0.05, holdout_fraction))
    holdout_n = max(1, int(math.ceil(len(rows) * holdout_fraction)))
    return _metrics(rows[-holdout_n:])


def _profitability_gate(
    market_counts: dict[str, int],
    *,
    min_after_cost_trades: int,
) -> dict[str, Any]:
    trades = int(market_counts.get("trades", 0))
    decision = "collect_only"
    reason = (
        "No dataset source gets live trading weight until it has an after-cost "
        f"market backtest with at least {min_after_cost_trades} matched trades."
    )
    if trades < min_after_cost_trades:
        reason += f" Current collected trade rows: {trades}."
    return {
        "decision": decision,
        "minimum_after_cost_trades": min_after_cost_trades,
        "market_history": market_counts,
        "reason": reason,
    }


def _market_history_counts(db_path: Path) -> dict[str, int]:
    if not Path(db_path).exists():
        return {"markets": 0, "candles": 0, "trades": 0}
    with sqlite3.connect(db_path) as conn:
        return {
            "markets": _table_count(conn, "dataset_kalshi_markets"),
            "candles": _table_count(conn, "dataset_kalshi_candles"),
            "trades": _table_count(conn, "dataset_kalshi_trades"),
        }


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    if not _table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _mae(errors: list[float]) -> float:
    return sum(abs(error) for error in errors) / len(errors)


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 4)
