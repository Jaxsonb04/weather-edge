"""Backfill the Kalshi-correct settlement truth (CLISFO daily max) from NCEI.

The live CLISFO scrape (``google_weather_cache.fetch_recent_clisfo_settlements``)
only reaches back a few days, so ``clisfo_settlements`` holds ~26 days — far too
few to fit/validate the calibration-edge changes on the truth Kalshi settles on.

NCEI GHCN-Daily TMAX for KSFO (station USW00023234) is the archived official
daily maximum and was validated to match the live CLISFO scrape EXACTLY on all
26 overlapping days (diff distribution {0: 26}). This pulls that archive (years
of history) into ``clisfo_settlements`` so the deep Kalshi-correct truth exists.

Safety / provenance:
  * Adds a nullable ``source`` column (additive; the live scrape INSERT, which
    names its columns, is unaffected).
  * Backfilled rows are tagged ``source='ghcn_backfill'`` and inserted with
    ON CONFLICT(local_date) DO NOTHING, so a real CLISFO scrape is NEVER
    overwritten — the live scrape stays authoritative for the dates it covers,
    and GHCN only fills historical gaps. Re-running is idempotent and reversible
    (``DELETE FROM clisfo_settlements WHERE source='ghcn_backfill'``).

Default is a DRY RUN (pull + validate + report, no writes). Pass ``--apply`` to
write. Read-only against the network; only ``--apply`` mutates the DB.

    python backfill_clisfo_from_ghcn.py            # dry run
    python backfill_clisfo_from_ghcn.py --apply     # write the backfill
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import urllib.request
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

GHCN_STATION = "USW00023234"  # San Francisco Intl AP (KSFO)
NCEI_URL = (
    "https://www.ncei.noaa.gov/access/services/data/v1?dataset=daily-summaries"
    "&stations={station}&dataTypes=TMAX&startDate={start}&endDate={end}"
    "&units=standard&format=json"
)
DEFAULT_DB = Path(__file__).resolve().parent / "weather.db"
DEFAULT_START = "2015-01-01"


def _cohort(high: int) -> str:
    if high < 60:
        return "cold"
    if high < 70:
        return "normal"
    if high < 80:
        return "warm"
    return "hot"


def fetch_ghcn_tmax(station: str, start: str, end: str, *, timeout: int = 120) -> dict[str, int]:
    """Date(ISO) -> integer daily max (F) from NCEI GHCN-Daily."""

    url = NCEI_URL.format(station=station, start=start, end=end)
    request = urllib.request.Request(url, headers={"user-agent": "weatheredge-backfill/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        rows = json.load(response)
    out: dict[str, int] = {}
    for row in rows:
        iso, tmax = row.get("DATE"), row.get("TMAX")
        if iso and tmax not in (None, ""):
            out[iso] = round(float(tmax))
    return out


def _existing(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        d: int(h)
        for d, h in conn.execute("SELECT local_date, max_temperature_f FROM clisfo_settlements")
        if h is not None
    }


def _has_source_column(conn: sqlite3.Connection) -> bool:
    return any(r[1] == "source" for r in conn.execute("PRAGMA table_info(clisfo_settlements)"))


def validate(existing: dict[str, int], ghcn: dict[str, int]) -> tuple[int, int]:
    """Return (exact_matches, overlap) of GHCN vs the already-stored CLISFO values."""

    overlap = [d for d in existing if d in ghcn]
    exact = sum(1 for d in overlap if ghcn[d] == existing[d])
    return exact, len(overlap)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--station", default=GHCN_STATION)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--apply", action="store_true", help="write the backfill (default: dry run)")
    args = parser.parse_args()

    end = date.today().isoformat()
    print(f"NCEI GHCN-Daily TMAX  station={args.station}  {args.start}..{end}")
    ghcn = fetch_ghcn_tmax(args.station, args.start, end)
    print(f"  fetched {len(ghcn)} daily-max days")

    if not args.db.exists():
        print(f"ERROR: db not found: {args.db}")
        return 1
    conn = sqlite3.connect(args.db)
    try:
        existing = _existing(conn)
        exact, overlap = validate(existing, ghcn)
        print(f"  existing clisfo_settlements rows: {len(existing)}")
        if overlap:
            pct = 100 * exact / overlap
            print(f"  VALIDATION vs live scrape: {exact}/{overlap} exact ({pct:.0f}%)")
            if exact != overlap:
                print("  WARNING: GHCN disagrees with the live scrape on some days — inspect before --apply")
        to_add = {d: h for d, h in ghcn.items() if d not in existing}
        cohorts = Counter(_cohort(h) for h in {**ghcn, **existing}.values())
        print(f"  new days to insert: {len(to_add)}   (existing scrapes are never overwritten)")
        print(f"  post-backfill cohorts: {dict(cohorts)}  warm+hot={cohorts['warm'] + cohorts['hot']}")

        if not args.apply:
            print("\nDRY RUN — no writes. Re-run with --apply to backfill.")
            return 0

        if exact != overlap:
            print("\nABORT: validation mismatch; not writing. Investigate the disagreeing days first.")
            return 1

        if not _has_source_column(conn):
            conn.execute("ALTER TABLE clisfo_settlements ADD COLUMN source TEXT")
            conn.execute(
                "UPDATE clisfo_settlements SET source='clisfo_scrape' WHERE source IS NULL"
            )
        now_iso = datetime.now(timezone.utc).isoformat()
        conn.executemany(
            """
            INSERT INTO clisfo_settlements (local_date, max_temperature_f, fetched_at, source)
            VALUES (?, ?, ?, 'ghcn_backfill')
            ON CONFLICT(local_date) DO NOTHING
            """,
            [(d, h, now_iso) for d, h in sorted(to_add.items())],
        )
        conn.commit()
        total = conn.execute("SELECT count(*) FROM clisfo_settlements").fetchone()[0]
        print(f"\nAPPLIED. clisfo_settlements now has {total} rows (+{len(to_add)} ghcn_backfill).")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
