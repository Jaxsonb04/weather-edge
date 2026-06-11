from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
FORECASTER = ROOT / "forecaster"
if str(FORECASTER) not in sys.path:
    sys.path.insert(0, str(FORECASTER))

import dashboard_payload
import google_weather_cache
from forecast_scoring import is_clean_next_day_forecast
from forecast_validation import chronological_unit_split_masks, forecast_unit_dates
from settlement_calendar import (
    integer_settlement_high_f,
    local_standard_date,
    utc_window_for_local_standard_date,
)
from sfo_kalshi_quant.forecast import SfoForecasterAdapter


SFO_TZ = ZoneInfo("America/Los_Angeles")


def _fetched_iso(local_day: date, hour: int = 23, minute: int = 30) -> str:
    return (
        datetime.combine(local_day, time(hour, minute), tzinfo=SFO_TZ)
        .astimezone(timezone.utc)
        .isoformat()
    )


def _create_blend_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE forecast_blend_daily_high (
            fetched_at TEXT NOT NULL,
            target_date TEXT NOT NULL,
            lead_hours REAL,
            method TEXT NOT NULL,
            predicted_high_f REAL NOT NULL,
            google_high_f REAL,
            nws_high_f REAL,
            open_meteo_high_f REAL,
            history_high_f REAL,
            google_weight REAL,
            nws_weight REAL,
            open_meteo_weight REAL,
            history_weight REAL,
            station_adjustment_f REAL,
            fresh_station_count INTEGER,
            source_count INTEGER,
            time_zone TEXT,
            max_calls_per_day INTEGER,
            calls_used_today INTEGER,
            details_json TEXT,
            actual_high_f REAL,
            abs_error_f REAL,
            scored_at TEXT
        )
        """
    )


def _insert_blend(
    conn: sqlite3.Connection,
    *,
    target: date,
    fetched_at: str,
    predicted: float,
    actual: float,
    google: float | None = None,
    nws: float | None = None,
    open_meteo: float | None = None,
    history: float | None = None,
    details: dict | None = None,
    refresh: int = 1,
) -> None:
    conn.execute(
        """
        INSERT INTO forecast_blend_daily_high (
            fetched_at, target_date, lead_hours, method, predicted_high_f,
            google_high_f, nws_high_f, open_meteo_high_f, history_high_f,
            google_weight, nws_weight, open_meteo_weight, history_weight,
            station_adjustment_f, fresh_station_count, source_count,
            time_zone, max_calls_per_day, calls_used_today, details_json,
            actual_high_f, abs_error_f, scored_at
        )
        VALUES (?, ?, 20, 'test blend', ?, ?, ?, ?, ?, 0.4, 0.3, 0.2, 0.1,
                0, 3, 4, 'America/Los_Angeles', 6, ?, ?, ?, ?, ?)
        """,
        (
            fetched_at,
            target.isoformat(),
            predicted,
            google,
            nws,
            open_meteo,
            history,
            refresh,
            json.dumps(details or {}),
            actual,
            abs(predicted - actual),
            datetime.now(timezone.utc).isoformat(),
        ),
    )


def _write_ab_test_results(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps({"target_daily_high_next_day": {"chart": {"daily": rows}}}),
        encoding="utf-8",
    )


def test_clean_next_day_forecast_excludes_same_day_lock_and_floor():
    target = date(2026, 6, 4)
    assert is_clean_next_day_forecast(target, _fetched_iso(date(2026, 6, 3)), "{}")
    assert not is_clean_next_day_forecast(target, _fetched_iso(target, 9), "{}")
    assert not is_clean_next_day_forecast(
        target,
        _fetched_iso(date(2026, 6, 3)),
        {"observed_high_decision": {"mode": "lock"}},
    )
    assert not is_clean_next_day_forecast(
        target,
        _fetched_iso(date(2026, 6, 3)),
        {"observed_high_decision": {"mode": "floor"}},
    )


def test_forecast_success_uses_last_clean_prior_day_snapshot_not_same_day_lock():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "weather.db"
        with sqlite3.connect(db_path) as conn:
            _create_blend_table(conn)
            target = date(2026, 6, 4)
            _insert_blend(
                conn,
                target=target,
                fetched_at=_fetched_iso(date(2026, 6, 3), 12),
                predicted=65,
                actual=70,
                refresh=1,
            )
            _insert_blend(
                conn,
                target=target,
                fetched_at=_fetched_iso(date(2026, 6, 3), 23),
                predicted=69,
                actual=70,
                refresh=2,
            )
            _insert_blend(
                conn,
                target=target,
                fetched_at=_fetched_iso(target, 10),
                predicted=70,
                actual=70,
                details={"observed_high_decision": {"mode": "lock"}},
                refresh=3,
            )

        result = dashboard_payload.load_forecast_success(db_path)

        assert result["available"]
        assert result["scoredCount"] == 2
        assert result["allScoredCount"] == 3
        assert result["excludedOperationalCount"] == 1
        assert result["dailyMae"] == 1.0
        assert result["snapshotMae"] == 3.0
        assert result["dailyRows"][0]["targetDate"] == target.isoformat()
        assert result["dailyRows"][0]["predicted"] == 69.0
        assert result["dailyRows"][0]["actual"] == 70.0
        assert {row["scoreCategory"] for row in result["recentRows"]} == {"clean_next_day"}
        assert result["sameDayContext"]["count"] == 1


def _adaptive_weights_for_db(db_path: Path):
    old_path = google_weather_cache.DB_PATH
    old_cache = getattr(google_weather_cache.adaptive_blend_weights, "_cached", None)
    if hasattr(google_weather_cache.adaptive_blend_weights, "_cached"):
        delattr(google_weather_cache.adaptive_blend_weights, "_cached")
    google_weather_cache.DB_PATH = db_path
    try:
        return google_weather_cache.adaptive_blend_weights()
    finally:
        google_weather_cache.DB_PATH = old_path
        if hasattr(google_weather_cache.adaptive_blend_weights, "_cached"):
            delattr(google_weather_cache.adaptive_blend_weights, "_cached")
        if old_cache is not None:
            google_weather_cache.adaptive_blend_weights._cached = old_cache


def test_adaptive_weights_learn_from_clean_rows_not_same_day_locks():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "weather.db"
        with sqlite3.connect(db_path) as conn:
            _create_blend_table(conn)
            start = date(2026, 5, 25)
            for offset in range(16):
                target = start + timedelta(days=offset)
                _insert_blend(
                    conn,
                    target=target,
                    fetched_at=_fetched_iso(target - timedelta(days=1)),
                    predicted=72,
                    actual=70,
                    google=70,
                    nws=80,
                    open_meteo=80,
                    history=80,
                )
                _insert_blend(
                    conn,
                    target=target,
                    fetched_at=_fetched_iso(target, 10),
                    predicted=70,
                    actual=70,
                    google=80,
                    nws=70,
                    open_meteo=80,
                    history=80,
                    details={"observed_high_decision": {"mode": "lock"}},
                )

        weights, metadata = _adaptive_weights_for_db(db_path)

        assert metadata["mode"] == "adaptive"
        assert metadata["scored_days"] == 16
        assert metadata["source_mae_f"]["google"] == 0.0
        assert metadata["source_mae_f"]["nws"] == 10.0
        assert metadata["holdout"]["candidate_mae_f"] < metadata["holdout"]["base_mae_f"]
        assert weights["google"] > weights["nws"]


def test_adaptive_weights_stay_base_below_minimum_scored_days():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "weather.db"
        with sqlite3.connect(db_path) as conn:
            _create_blend_table(conn)
            start = date(2026, 6, 10)
            for offset in range(5):
                target = start + timedelta(days=offset)
                _insert_blend(
                    conn,
                    target=target,
                    fetched_at=_fetched_iso(target - timedelta(days=1)),
                    predicted=72,
                    actual=70,
                    google=70,
                    nws=80,
                    open_meteo=80,
                    history=80,
                )

        weights, metadata = _adaptive_weights_for_db(db_path)

        assert metadata["mode"] == "base"
        assert metadata["scored_days"] == 5
        assert weights == google_weather_cache.BLEND_WEIGHTS


def test_adaptive_weights_rejected_when_holdout_does_not_improve():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "weather.db"
        with sqlite3.connect(db_path) as conn:
            _create_blend_table(conn)
            start = date(2026, 5, 25)
            for offset in range(16):
                target = start + timedelta(days=offset)
                # Source skill flips for the most recent third: weights
                # learned from the older days must not be promoted.
                google_good = offset < 10
                _insert_blend(
                    conn,
                    target=target,
                    fetched_at=_fetched_iso(target - timedelta(days=1)),
                    predicted=72,
                    actual=70,
                    google=70 if google_good else 84,
                    nws=80 if google_good else 70,
                    open_meteo=80,
                    history=80,
                )

        weights, metadata = _adaptive_weights_for_db(db_path)

        assert metadata["mode"] == "base"
        assert "holdout" in metadata
        assert weights == google_weather_cache.BLEND_WEIGHTS


def test_clean_blend_outcomes_are_point_in_time_last_prior_day_rows():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "weather.db"
        with sqlite3.connect(db_path) as conn:
            _create_blend_table(conn)
            target = date(2026, 6, 4)
            _insert_blend(
                conn,
                target=target,
                fetched_at=_fetched_iso(date(2026, 6, 3), 18),
                predicted=66,
                actual=70,
            )
            _insert_blend(
                conn,
                target=target,
                fetched_at=_fetched_iso(date(2026, 6, 3), 23),
                predicted=69,
                actual=69.6,
            )
            _insert_blend(
                conn,
                target=target,
                fetched_at=_fetched_iso(target, 9),
                predicted=70,
                actual=70,
                details={"observed_high_decision": {"mode": "floor"}},
            )

        outcomes = SfoForecasterAdapter(root).load_clean_blend_outcomes()

        assert len(outcomes) == 1
        assert outcomes[0].local_date == target
        assert outcomes[0].predicted_high_f == 69
        assert outcomes[0].actual_high_f == 70
        assert outcomes[0].model_name == "clean_blend"


def test_auto_calibration_prefers_clean_blend_when_enough_rows():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        db_path = root / "weather.db"
        with sqlite3.connect(db_path) as conn:
            _create_blend_table(conn)
            start = date(2026, 1, 1)
            for offset in range(30):
                target = start + timedelta(days=offset)
                _insert_blend(
                    conn,
                    target=target,
                    fetched_at=_fetched_iso(target - timedelta(days=1), 23),
                    predicted=68 + offset % 3,
                    actual=69.6,
                )
        _write_ab_test_results(
            root / "ab_test_results.json",
            [{"date": "2025-12-31", "lstm": 64, "actual": 64.4}],
        )

        outcomes = SfoForecasterAdapter(root).load_calibration_outcomes("auto", min_clean_blend=30)

        assert len(outcomes) == 30
        assert {row.model_name for row in outcomes} == {"clean_blend"}
        assert {row.actual_high_f for row in outcomes} == {70.0}


def test_auto_calibration_falls_back_to_lstm_without_clean_depth():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_ab_test_results(
            root / "ab_test_results.json",
            [{"date": "2025-12-31", "lstm": 64, "actual": 64.5}],
        )

        outcomes = SfoForecasterAdapter(root).load_calibration_outcomes("auto", min_clean_blend=30)

        assert len(outcomes) == 1
        assert outcomes[0].model_name == "lstm"
        assert outcomes[0].actual_high_f == 65.0


def test_chronological_unit_split_keeps_daily_target_dates_out_of_multiple_splits():
    index = pd.date_range("2026-01-01", periods=24 * 40, freq="h", tz="UTC")
    masks = chronological_unit_split_masks(index, "target_daily_high_next_day")
    units = forecast_unit_dates(index, "target_daily_high_next_day")

    split_units = {
        name: set(units[mask])
        for name, mask in masks.items()
    }

    assert split_units["train"].isdisjoint(split_units["val"])
    assert split_units["train"].isdisjoint(split_units["test"])
    assert split_units["val"].isdisjoint(split_units["test"])


def test_settlement_calendar_uses_pacific_standard_report_day():
    # 2026-06-08 00:30 PDT is still 2026-06-07 in Pacific standard time.
    observed = datetime(2026, 6, 8, 7, 30, tzinfo=timezone.utc)
    assert local_standard_date(observed) == date(2026, 6, 7)

    start_utc, end_utc = utc_window_for_local_standard_date(date(2026, 6, 8))
    assert start_utc == datetime(2026, 6, 8, 8, 0, tzinfo=timezone.utc)
    assert end_utc == datetime(2026, 6, 9, 8, 0, tzinfo=timezone.utc)


def test_settlement_high_rounds_to_integer_report_value():
    assert integer_settlement_high_f(69.4) == 69.0
    assert integer_settlement_high_f(69.5) == 70.0
    assert integer_settlement_high_f(69.6) == 70.0
