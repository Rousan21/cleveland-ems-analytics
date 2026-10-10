"""Time-window validation and privacy-preserving aggregate statistics."""
from datetime import date, datetime, time, timedelta, timezone
from statistics import median
from zoneinfo import ZoneInfo

from sqlalchemy import select, func
from db import EMSCall, SyncRun, SessionLocal

LOCAL = ZoneInfo("America/New_York")
WINDOWS = {"24h": 1, "7d": 7, "30d": 30, "90d": 90, "1y": 365, "all": None, "custom": None}


def get_bounds(window: str, start_date: str | None, end_date: str | None, now: datetime | None = None):
    if window not in WINDOWS:
        raise ValueError("Invalid date range")
    now = now or datetime.now(timezone.utc)
    if window == "custom":
        if not start_date or not end_date:
            raise ValueError("Custom range requires start and end dates")
        try:
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)
        except ValueError as e:
            raise ValueError("Use dates in YYYY-MM-DD format") from e
        if end < start:
            raise ValueError("End date must not be before start date")
        if (end - start).days > 3650:
            raise ValueError("Custom range must be 10 years or less")
        return (datetime.combine(start, time.min, LOCAL).astimezone(timezone.utc),
                datetime.combine(end + timedelta(days=1), time.min, LOCAL).astimezone(timezone.utc))
    days = WINDOWS[window]
    return (now - timedelta(days=days), now) if days else (None, now)


def as_utc(value):
    if value is None:
        return None
    # SQLite often returns timezone-naive values despite timezone=True; these represent UTC.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def summarize(*, window="30d", priority="all", start_date=None, end_date=None, now=None):
    start, end = get_bounds(window, start_date, end_date, now)
    daily = {}
    by_priority = {}
    by_hour = {str(i): 0 for i in range(24)}
    dispatch_intervals = []
    scene_intervals = []
    count = 0

    # Stream ORM rows in batches. Loading years of EMS records with .all()
    # would exhaust a small free Render instance's memory unnecessarily.
    with SessionLocal() as db:
        query = select(EMSCall).where(EMSCall.dispatch_time.is_not(None), EMSCall.dispatch_time < end)
        if start:
            query = query.where(EMSCall.dispatch_time >= start)
        if priority != "all":
            if priority not in {"1", "2", "3"}:
                raise ValueError("Invalid priority")
            query = query.where(EMSCall.priority == priority)
        most_recent = db.scalar(select(func.max(EMSCall.dispatch_time)))
        total_stored = db.scalar(select(func.count(EMSCall.object_id))) or 0
        last_success = db.scalar(select(SyncRun).where(SyncRun.status == "success").order_by(SyncRun.finished_at.desc()).limit(1))
        last_attempt = db.scalar(select(SyncRun).order_by(SyncRun.finished_at.desc()).limit(1))
        last_success_at = last_success.finished_at if last_success else None
        last_sync_failed = bool(last_attempt and last_attempt.status != "success")

        # yield_per streams database rows rather than retaining large ORM lists.
        for call in db.scalars(query).yield_per(1000):
            count += 1
            dispatched = as_utc(call.dispatch_time).astimezone(LOCAL)
            day = dispatched.date().isoformat()
            daily[day] = daily.get(day, 0) + 1
            by_hour[str(dispatched.hour)] += 1
            key = str(call.priority or "Unknown")
            by_priority[key] = by_priority.get(key, 0) + 1
            received = as_utc(call.call_time)
            if received:
                for target, output in [(call.dispatch_time, dispatch_intervals), (call.scene_time, scene_intervals)]:
                    arrived = as_utc(target)
                    if arrived:
                        minutes = (arrived - received).total_seconds() / 60
                        if minutes >= 0:
                            output.append(minutes)

    def iso(dt):
        return as_utc(dt).isoformat() if dt else None

    return {
        "window": window, "priority": priority,
        "records": count, "total_stored": total_stored,
        "median_call_to_dispatch_min": round(median(dispatch_intervals), 1) if dispatch_intervals else None,
        "median_call_to_scene_min": round(median(scene_intervals), 1) if scene_intervals else None,
        "daily": [{"date": k, "count": daily[k]} for k in sorted(daily)],
        "hours": [{"hour": int(k), "count": v} for k, v in by_hour.items()],
        "priorities": [{"priority": k, "count": v} for k, v in sorted(by_priority.items())],
        "latest_call": iso(most_recent),
        "last_successful_sync": iso(last_success_at),
        "last_sync_failed": last_sync_failed,
        "source": "City of Cleveland Division of EMS / ArcGIS",
        "note": "Includes records with dispatch timestamps. Time intervals are call-to-event, not official EMS performance measures.",
    }
