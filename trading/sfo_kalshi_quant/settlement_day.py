"""Single source of truth for the Kalshi/NWS settlement day in trading code.

The NWS daily climate report (and therefore Kalshi settlement) buckets a day
by the station's local *standard* time year-round, so trading must define
"today/tomorrow/rolling" with fixed UTC-8, not civil America/Los_Angeles
dates. During DST the two disagree between 23:00 and 24:00 PST (00:00-01:00
PDT); civil dates would target, gate, freshness-check, and auto-settle the
wrong Kalshi day in that window. This mirrors
forecaster/settlement_calendar.py, which the trading package cannot import.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from .config import SFO_TZ

PACIFIC_STANDARD_TZ = timezone(timedelta(hours=-8), "PST")

# IANA spelling of fixed UTC-8 (POSIX sign convention), for APIs that take a
# timezone name and aggregate daily values over it (Open-Meteo, IEM).
IANA_FIXED_PST = "Etc/GMT+8"


def settlement_clock(now: datetime | None = None) -> datetime:
    """Return the current moment on the fixed-PST settlement clock.

    Naive inputs are assumed to be civil SFO wall-clock time, the historical
    convention for the ``now`` test hooks.
    """

    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=SFO_TZ)
    return moment.astimezone(PACIFIC_STANDARD_TZ)


def settlement_today(now: datetime | None = None) -> date:
    """Return the settlement day currently being measured at the station."""

    return settlement_clock(now).date()
