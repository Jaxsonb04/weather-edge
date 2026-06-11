from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import math


PACIFIC_STANDARD_TZ = timezone(timedelta(hours=-8), "PST")


def local_standard_date(timestamp: datetime) -> date:
    """Return the NWS/Kalshi report date for a Pacific observation timestamp."""

    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(PACIFIC_STANDARD_TZ).date()


def today_local_standard(now: datetime | None = None) -> date:
    now = now or datetime.now(timezone.utc)
    return local_standard_date(now)


def utc_window_for_local_standard_date(local_date: str | date) -> tuple[datetime, datetime]:
    if isinstance(local_date, str):
        day = date.fromisoformat(local_date)
    else:
        day = local_date
    start = datetime.combine(day, datetime.min.time(), tzinfo=PACIFIC_STANDARD_TZ)
    end = start + timedelta(days=1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def integer_settlement_high_f(value: object) -> float | None:
    if value is None:
        return None
    high = float(value)
    if not math.isfinite(high):
        return None
    return float(math.floor(high + 0.5))
