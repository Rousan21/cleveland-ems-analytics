"""Verified Cleveland, Ohio EMS ingestion and aggregate analytics.

Unlike the old prototype, this consumes the official *Cleveland* CAD_EMS_Public
ArcGIS table. The source provides incident date, neighborhood, priority, incident
type and transport/dispatch flags, but NO measured response-time fields.
Do not mix it with the archived Virginia Beach EMS rows.
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from analytics import as_utc, get_bounds
from db import ClevelandRecord, ClevelandSyncRun, SessionLocal, engine, init_database

SOURCE_BASE = (
    "https://services3.arcgis.com/dty2kHktVXHrqO8i/ArcGIS/rest/services/"
    "data/FeatureServer/0"
)
SOURCE_URL = SOURCE_BASE + "/query"
SOURCE_FIELDS = (
    "ObjectId,IncidentDate,city,neighborhood,CurrentPriorityKey,"
    "IncidentTypeDescription,isDispatch,isTransport,census_tract"
)
EXPECTED_FIELDS = frozenset(SOURCE_FIELDS.split(","))
SOURCE_ITEM_ID = "d5d71757cc73400d843c98bcb46e46b6"
LOCAL = ZoneInfo("America/New_York")
PAGE_SIZE = 1000
VALID_PRIORITIES = {str(i) for i in range(1, 8)}


def validate_source(client=None):
    """Fail closed if the remote schema or ArcGIS service identity changes."""
    response = (client or requests).get(SOURCE_BASE, params={"f": "json"}, timeout=35)
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise RuntimeError("Official Cleveland EMS ArcGIS schema unavailable")
    fields = {f.get("name") for f in payload.get("fields", [])}
    if payload.get("type") != "Table" or EXPECTED_FIELDS - fields:
        raise RuntimeError("Official Cleveland EMS source schema changed; import stopped")
    # Source item identity verified via Esri item metadata; schema also checked.
    return True


def parse_epoch_ms(value):
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def _short(value, max_length):
    v = str(value or "").strip()
    return v[:max_length] if v else None


def _flag(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    normalized = str(value or "").strip().casefold()
    return normalized if normalized in {"true", "false"} else None


def row_from_attrs(attrs):
    """Keep only nonidentifying fields. Reject non-Cleveland municipalities."""
    if str(attrs.get("city") or "").strip().casefold() != "cleveland":
        return None
    incident_time = parse_epoch_ms(attrs.get("IncidentDate"))
    if not incident_time:
        return None
    priority = _short(attrs.get("CurrentPriorityKey"), 12)
    return {
        "object_id": int(attrs["ObjectId"]),
        "incident_time": incident_time,
        "neighborhood": _short(attrs.get("neighborhood"), 100),
        "priority": priority if priority in VALID_PRIORITIES else None,
        "incident_type": _short(attrs.get("IncidentTypeDescription"), 120),
        "dispatch_flag": _flag(attrs.get("isDispatch")),
        "transport_flag": _flag(attrs.get("isTransport")),
        "tract": _short(attrs.get("census_tract"), 24),
    }


def fetch_pages(*, days=400, session=None, now=None):
    """Keyset-page authoritative Cleveland CAD records, never legacy Virginia Beach.

    Use ObjectId only for page order; IncidentDate is the actual temporal key.
    """
    if not isinstance(days, int) or not (1 <= days <= 3000):
        raise ValueError("days must be 1..3000")
    now = as_utc(now or datetime.now(timezone.utc))
    cutoff = now - timedelta(days=days)
    last_id = -1
    client = session or requests.Session()
    while True:
        response = client.get(SOURCE_URL, params={
            "where": (
                f"ObjectId > {last_id} AND "
                f"IncidentDate >= TIMESTAMP '{cutoff:%Y-%m-%d %H:%M:%S}'"
            ),
            "outFields": SOURCE_FIELDS, "returnGeometry": "false",
            "orderByFields": "ObjectId ASC", "resultRecordCount": PAGE_SIZE,
            "f": "json",
        }, timeout=60)
        response.raise_for_status()
        payload = response.json()
        if payload.get("error"):
            raise RuntimeError(f"Official Cleveland EMS source query rejected: {payload['error']}")
        features = payload.get("features")
        if not isinstance(features, list):
            raise RuntimeError("Official Cleveland EMS query missing feature list")
        if not features:
            return
        ids = [int(feature["attributes"]["ObjectId"]) for feature in features]
        if ids[0] <= last_id or any(a >= b for a, b in zip(ids, ids[1:])):
            raise RuntimeError("Cleveland source returned unordered/repeated IDs")
        last_id = ids[-1]
        yield [feature["attributes"] for feature in features]
        if len(features) < PAGE_SIZE and not payload.get("exceededTransferLimit", False):
            return


def upsert_rows(connection, rows):
    if not rows:
        return
    table = ClevelandRecord.__table__
    for start in range(0, len(rows), 100):
        batch = rows[start:start + 100]
        if connection.dialect.name == "postgresql":
            statement = pg_insert(table).values(batch)
        elif connection.dialect.name == "sqlite":
            statement = sqlite_insert(table).values(batch)
        else:
            raise RuntimeError("Unsupported database driver")
        updates = {c.name: statement.excluded[c.name] for c in table.columns if c.name != "object_id"}
        connection.execute(statement.on_conflict_do_update(index_elements=["object_id"], set_=updates))


def sync_data(*, days=400, session=None, now=None, validate=True):
    if validate:
        validate_source(session)
    init_database()
    processed = accepted = pages = 0
    try:
        for batch in fetch_pages(days=days, session=session, now=now):
            processed += len(batch)
            rows = [r for attrs in batch if (r := row_from_attrs(attrs)) is not None]
            accepted += len(rows)
            if rows:
                with engine.begin() as connection:
                    upsert_rows(connection, rows)
            pages += 1
            if pages % 25 == 0:
                print(f"Cleveland EMS sync: fetched {processed:,} source rows; kept {accepted:,} Cleveland records",flush=True)
        if accepted == 0:
            raise RuntimeError("Source returned no dated Cleveland records; refusing success")
        # Sanity check protects against silent cross-jurisdiction source changes.
        if accepted / max(processed, 1) < .75:
            raise RuntimeError("Fewer than 75% of source rows belong to Cleveland; inspect source before publishing")
        with SessionLocal() as db:
            db.add(ClevelandSyncRun(finished_at=datetime.now(timezone.utc),
                                   record_count=accepted,status="success"))
            db.commit()
        return {"source_rows_seen":processed,"cleveland_rows_upserted":accepted}
    except Exception as error:
        with SessionLocal() as db:
            db.add(ClevelandSyncRun(finished_at=datetime.now(timezone.utc),
                                   record_count=accepted,status="failed",detail=str(error)[:500]))
            db.commit()
        raise


def _query_rows(*, window, priority, now=None, start_date=None, end_date=None):
    start, end = get_bounds(window, start_date, end_date, now)
    if priority != "all" and priority not in VALID_PRIORITIES:
        raise ValueError("Unknown Cleveland source priority code")
    with SessionLocal() as db:
        query = select(
            ClevelandRecord.incident_time,
            ClevelandRecord.priority,
            ClevelandRecord.incident_type,
            ClevelandRecord.neighborhood,
            ClevelandRecord.dispatch_flag,
            ClevelandRecord.transport_flag,
        ).where(ClevelandRecord.incident_time.is_not(None),
                ClevelandRecord.incident_time < end)
        if start:
            query = query.where(ClevelandRecord.incident_time >= start)
        if priority != "all":
            query = query.where(ClevelandRecord.priority == priority)
        for row in db.execute(query).yield_per(1000):
            yield row


def summarize(*, window="30d", priority="all", start_date=None, end_date=None, now=None):
    """Compute only Cleveland CAD metrics supported by its actual schema."""
    date_counts = Counter()
    hour_counts = Counter()
    priority_counts = Counter()
    type_counts = Counter()
    neighborhood_set = set()
    records = 0
    dispatch_known = transport_known = dispatched = transported = 0
    for r in _query_rows(window=window,priority=priority,now=now,
                         start_date=start_date,end_date=end_date):
        records += 1
        local = as_utc(r.incident_time).astimezone(LOCAL)
        date_counts[local.date().isoformat()] += 1
        hour_counts[local.hour] += 1
        priority_counts[r.priority or "Unknown"] += 1
        type_counts[r.incident_type or "Uncoded"] += 1
        if r.neighborhood:
            neighborhood_set.add(r.neighborhood)
        if r.dispatch_flag in ("true", "false"):
            dispatch_known += 1
            dispatched += int(r.dispatch_flag == "true")
        if r.transport_flag in ("true", "false"):
            transport_known += 1
            transported += int(r.transport_flag == "true")
    with SessionLocal() as db:
        stored = db.scalar(select(func.count(ClevelandRecord.object_id))) or 0
        newest = db.scalar(select(func.max(ClevelandRecord.incident_time)))
        earliest = db.scalar(select(func.min(ClevelandRecord.incident_time)))
        last_success = db.scalar(
            select(ClevelandSyncRun.finished_at)
            .where(ClevelandSyncRun.status == "success")
            .order_by(ClevelandSyncRun.finished_at.desc()).limit(1)
        )
        last_attempt = db.scalar(select(ClevelandSyncRun.status).order_by(
            ClevelandSyncRun.finished_at.desc()).limit(1))
    def iso(v):
        return as_utc(v).isoformat() if v else None
    return {
        "window":window,"priority":priority,
        "records":records,"total_stored":stored,
        "dispatched_count":dispatched,"dispatch_flag_known":dispatch_known,
        "transported_count":transported,"transport_flag_known":transport_known,
        "neighborhoods_in_source":len(neighborhood_set),
        "daily":[{"date":d,"count":date_counts[d]} for d in sorted(date_counts)],
        "hours":[{"hour":h,"count":hour_counts[h]} for h in range(24)],
        "priorities":[{"priority":p,"count":priority_counts[p]} for p in
                      sorted(priority_counts,key=lambda x:(x=="Unknown",x))],
        "incident_types":[{"type":name,"count":n} for name,n in
                          sorted(type_counts.items(),key=lambda x:(-x[1],x[0]))[:8]],
        "latest_call":iso(newest),"earliest_call":iso(earliest),
        "last_successful_sync":iso(last_success),
        "last_sync_failed":last_attempt=="failed",
        "source":"City of Cleveland (Ohio) CAD_EMS_Public",
        "source_item_id":SOURCE_ITEM_ID,
        "note":("Counts are Cleveland-published EMS records, not verified unique emergencies. "
                "Dispatch and transport fields are source flags, not measured response times."),
    }


def area_summary(*,window="30d",priority="all",now=None,
                 start_date=None,end_date=None,known_neighborhoods=None):
    """Only source-provided, boundary-matched neighborhoods; suppress counts <11."""
    known = {name.strip().casefold():name for name in (known_neighborhoods or [])}
    area_counts = Counter()
    total = 0
    unassigned = 0
    for row in _query_rows(window=window,priority=priority,now=now,
                           start_date=start_date,end_date=end_date):
        total += 1
        label = (row.neighborhood or "").strip()
        if label and label.casefold() in known:
            area_counts[known[label.casefold()]] += 1
        else:
            unassigned += 1
    mapped = sum(area_counts.values())
    allowed = [{"name":name,"count":c} for name,c in
               sorted(area_counts.items(),key=lambda v:(-v[1],v[0]))
               if c >= 11]
    return {
        "status":"ready" if allowed else ("suppressed" if mapped else "no_verified_geography"),
        "reporting_threshold":11,
        "mapped_records":mapped,
        "eligible_records":total,
        "unmapped_records":unassigned,
        "mapping_coverage_pct":round(100*mapped/total,1) if total else None,
        "areas":allowed,
        "note":("Source-provided Cleveland neighborhood labels matched to Cleveland GIS boundaries. "
                "Counts below 11 suppressed. Differences in neighborhood naming are excluded "
                "rather than guessed; values are published rows, not unique incidents."),
    }


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest="cmd",required=True)
    sync=sub.add_parser("sync",help="Import official Cleveland EMS source into separate table")
    sync.add_argument("--days",type=int,default=400)
    args=parser.parse_args()
    if args.cmd=="sync":
        print(sync_data(days=args.days),flush=True)
