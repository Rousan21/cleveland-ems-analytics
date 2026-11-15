"""Measure late publication using successive citywide daily count snapshots.

The initial snapshot does not establish latency. We only report actual changes
between observations; no arbitrary 'complete' label is assigned to any day.
"""
import argparse
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import inspect, select

from db import EMSCall, PublicationSnapshot, SessionLocal, engine, init_database

LOCAL = ZoneInfo("America/New_York")
HISTORY_DAYS = 21


def _utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def capture_publication_snapshot(*, now: datetime | None = None, days: int = HISTORY_DAYS):
    """Capture 21 local calendar days of aggregated rows from the imported DB.

    A zero represents zero rows currently *published* for a date, not zero calls.
    Capturing old dates repeatedly reveals backfills and later source edits.
    """
    if not (2 <= days <= 90):
        raise ValueError("days must be between 2 and 90")
    now = _utc(now or datetime.now(timezone.utc))
    today = now.astimezone(LOCAL).date()
    first = today - timedelta(days=days - 1)
    cutoff = datetime.combine(first, time.min, LOCAL).astimezone(timezone.utc)
    init_database()
    counts = defaultdict(int)
    with SessionLocal() as db:
        values = db.scalars(
            select(EMSCall.dispatch_time)
            .where(EMSCall.dispatch_time.is_not(None), EMSCall.dispatch_time >= cutoff, EMSCall.dispatch_time <= now)
        ).yield_per(1000)
        for dispatch_time in values:
            local_day = _utc(dispatch_time).astimezone(LOCAL).date()
            if first <= local_day <= today:
                counts[local_day] += 1
        rows = [
            PublicationSnapshot(
                observed_at=now,
                dispatch_date=first + timedelta(days=i),
                published_rows=counts[first + timedelta(days=i)],
            )
            for i in range(days)
        ]
        db.add_all(rows)
        db.commit()
    return {"observed_at": now.isoformat(), "days_recorded": days}


def publication_history(*, now: datetime | None = None, days: int = 14):
    """Return observed first/latest counts, without estimating completeness.

    An empty table is normal before the first scheduled daily import.
    """
    if not (1 <= days <= HISTORY_DAYS):
        raise ValueError("days must be between 1 and 21")
    now = _utc(now or datetime.now(timezone.utc))
    today = now.astimezone(LOCAL).date()
    first = today - timedelta(days=days)
    base = {
        "status": "collecting",
        "latest_observation_at": None,
        "observations": 0,
        "days": [],
        "note": ("Counts reflect records available at each import, not verified incident volume. "
                 "A change in published rows is observable backfill/revision; no day is assumed complete."),
    }
    if not inspect(engine).has_table(PublicationSnapshot.__tablename__):
        return base
    with SessionLocal() as db:
        snapshots = db.scalars(
            select(PublicationSnapshot)
            .where(PublicationSnapshot.dispatch_date >= first,
                   PublicationSnapshot.dispatch_date < today,
                   PublicationSnapshot.observed_at <= now)
            .order_by(PublicationSnapshot.observed_at.asc(), PublicationSnapshot.id.asc())
        ).all()
    if not snapshots:
        return base
    observations = sorted(set(_utc(row.observed_at) for row in snapshots))
    groups = defaultdict(list)
    for row in snapshots:
        groups[row.dispatch_date].append(row)

    daily = []
    for day in sorted(groups):
        values = groups[day]
        earliest, latest = values[0], values[-1]
        daily.append({
            "date": day.isoformat(),
            "first_observed": earliest.published_rows,
            "latest_observed": latest.published_rows,
            "net_change": latest.published_rows - earliest.published_rows,
            "samples": len(values),
        })
    return {
        **base,
        "status": "observed_changes" if len(observations) >= 2 else "collecting",
        "latest_observation_at": observations[-1].isoformat(),
        "observations": len(observations),
        "days": daily,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Record citywide aggregate publication counts")
    parser.add_argument("command", choices=["capture"])
    args = parser.parse_args()
    if args.command == "capture":
        print(capture_publication_snapshot(), flush=True)
