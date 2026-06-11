from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from settlement_calendar import local_standard_date


OPERATIONAL_OBSERVED_MODES = {"floor", "lock"}


def parse_details_json(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        payload = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def observed_high_mode(details: dict) -> str | None:
    decision = details.get("observed_high_decision") if isinstance(details, dict) else None
    if not isinstance(decision, dict):
        return None
    mode = decision.get("mode")
    return str(mode).lower() if mode else None


def fetched_sfo_date(fetched_at: object) -> date | None:
    """Settlement-day (fixed PST) date of a fetch timestamp.

    A snapshot fetched between 00:00 and 01:00 PDT belongs to the previous
    settlement day, which is still in progress; civil dates would misclassify
    it as a same-day forecast for the next target.
    """

    if not fetched_at:
        return None
    try:
        fetched = datetime.fromisoformat(str(fetched_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return local_standard_date(fetched)


def parse_target_date(target_date: object) -> date | None:
    if isinstance(target_date, date):
        return target_date
    if not target_date:
        return None
    try:
        return date.fromisoformat(str(target_date))
    except ValueError:
        return None


def is_clean_next_day_forecast(
    target_date: object,
    fetched_at: object,
    details_json: object,
) -> bool:
    target = parse_target_date(target_date)
    fetched_local_date = fetched_sfo_date(fetched_at)
    if target is None or fetched_local_date is None:
        return False
    if target != fetched_local_date + timedelta(days=1):
        return False
    details = parse_details_json(details_json)
    return observed_high_mode(details) not in OPERATIONAL_OBSERVED_MODES


def forecast_score_category(
    target_date: object,
    fetched_at: object,
    details_json: object,
) -> str:
    if is_clean_next_day_forecast(target_date, fetched_at, details_json):
        return "clean_next_day"
    details = parse_details_json(details_json)
    if observed_high_mode(details) in OPERATIONAL_OBSERVED_MODES:
        return "same_day_operational"
    return "other_archived"
