"""Verified Cleveland, Ohio EMS ingestion and aggregate analytics.

Unlike the old prototype, this consumes the official *Cleveland* CAD_EMS_Public
ArcGIS table. The source provides incident date, neighborhood, priority, incident
type and transport/dispatch flags, but NO measured response-time fields.
Do not mix it with the archived Virginia Beach EMS rows.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone, time
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
COMMON_TYPE_LIMIT = 10  # Filter frequent source labels, not inferred medical groupings.
NON_REASON_TYPES = frozenset({"NO DISPATCH", "UNCODED"})


def is_incident_reason(label):
    """Exclude non-reason / administrative categories only from reason analytics."""
    return bool(label) and label.strip().upper() not in NON_REASON_TYPES




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


def common_incident_types():
    """Ten most frequent meaningful source incident reasons across imported dates.

    Omit ambiguous administrative/uncoded labels from the visitor's filter;
    do not delete those records from selected-period totals or transport rates.
    Short IDs keep the static URLs safe; original labels are not reclassified.
    """
    with SessionLocal() as db:
        rows = db.execute(
            select(ClevelandRecord.incident_type,
                   func.count(ClevelandRecord.object_id).label("n"))
            .where(ClevelandRecord.incident_type.is_not(None),
                   func.trim(ClevelandRecord.incident_type) != "",
                   func.upper(func.trim(ClevelandRecord.incident_type)).not_in(NON_REASON_TYPES))
            .group_by(ClevelandRecord.incident_type)
            .having(func.count(ClevelandRecord.object_id) >= 11)
            .order_by(func.count(ClevelandRecord.object_id).desc(),
                      ClevelandRecord.incident_type.asc())
            .limit(COMMON_TYPE_LIMIT)
        ).all()
    return [{"id":f"type_{i:02d}", "label":label}
            for i,(label,_) in enumerate(rows,1)]


def resolve_incident_type(incident_type):
    if incident_type == "all":
        return None
    for entry in common_incident_types():
        if entry["id"] == incident_type:
            return entry["label"]
    raise ValueError("Unknown Cleveland incident classification filter")


def _query_rows(*, window, priority, incident_type="all", now=None, start_date=None, end_date=None):
    start, end = get_bounds(window, start_date, end_date, now)
    if priority != "all" and priority not in VALID_PRIORITIES:
        raise ValueError("Unknown Cleveland source priority code")
    source_type_label = resolve_incident_type(incident_type)
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
        if source_type_label is not None:
            query = query.where(ClevelandRecord.incident_type == source_type_label)
        for row in db.execute(query).yield_per(1000):
            yield row



def select_comparable_calendar_days(date_counts, *, window, start, end):
    """Daily trend must not compare a short boundary day with 24-hour days.

    The overall selected-period counts remain unchanged: this affects only the
    plotted daily series, never the source totals, category counts or CSV export.
    Dates are evaluated in America/New_York to handle daylight-saving changes.
    A rolling 24h window cannot contain two complete local calendar days, so
    that view keeps the raw day splits with an explicit warning.
    """
    raw = [{"date":day, "count":date_counts[day]} for day in sorted(date_counts)]
    if not raw:
        return [], [], "No records available for a daily trend."
    if window == "24h":
        return raw, [], (
            "Rolling past-day view: local calendar dates are partial, so "
            "do not compare their daily heights."
        )
    end_local = as_utc(end).astimezone(LOCAL)
    start_local = as_utc(start).astimezone(LOCAL) if start else None
    excluded = set()

    # When importing historical rows for "all", the first imported day may
    # start partway through a day; do not imply it is a full 24-hour sample.
    if not start_local:
        excluded.add(raw[0]["date"])
    elif start_local.time() != time.min:
        excluded.add(start_local.date().isoformat())

    # end is exclusive; if it falls during a local day, that local day is
    # unfinished even if the source already published some records for it.
    if end_local.time() != time.min:
        excluded.add(end_local.date().isoformat())

    displayed = [item for item in raw if item["date"] not in excluded]
    dropped = [item for item in raw if item["date"] in excluded]
    if len(displayed) >= 2:
        return displayed, dropped, (
            "Trend compares complete Cleveland-local calendar dates only. "
            "Partial first/current dates are excluded from this graph, but "
            "their records remain in the summary totals and raw daily CSV. "
            "Published dates may still be revised later."
        )
    # If a sparse priority filter yields too few complete days, do not
    # manufacture a trend by reconnecting partially observed endpoints.
    return displayed, dropped, (
        "Not enough complete local calendar days for a meaningful daily trend. "
        "Try a longer window or All incident types; selected-period totals remain available."
    )


def summarize(*, window="30d", priority="all", incident_type="all", start_date=None, end_date=None, now=None):
    """Compute only Cleveland CAD metrics supported by its actual schema."""
    date_counts = Counter()
    hour_counts = Counter()
    priority_counts = Counter()
    type_counts = Counter()
    neighborhood_set = set()
    neighborhood_labeled_count = 0
    records = 0
    dispatch_known = transport_known = dispatched = transported = 0
    for r in _query_rows(window=window,priority=priority,incident_type=incident_type,now=now,
                         start_date=start_date,end_date=end_date):
        records += 1
        local = as_utc(r.incident_time).astimezone(LOCAL)
        date_counts[local.date().isoformat()] += 1
        hour_counts[local.hour] += 1
        priority_counts[r.priority or "Unknown"] += 1
        type_counts[r.incident_type or "Uncoded"] += 1
        if r.neighborhood:
            neighborhood_set.add(r.neighborhood)
            neighborhood_labeled_count += 1
        if r.dispatch_flag in ("true", "false"):
            dispatch_known += 1
            dispatched += int(r.dispatch_flag == "true")
        if r.transport_flag in ("true", "false"):
            transport_known += 1
            transported += int(r.transport_flag == "true")
    start_bound, end_bound = get_bounds(window, start_date, end_date, now)
    chart_days, partial_days, chart_note = select_comparable_calendar_days(
        date_counts, window=window, start=start_bound, end=end_bound
    )
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
    reason_counts = {label:n for label,n in type_counts.items()
                     if is_incident_reason(label)}
    reason_total = sum(reason_counts.values())
    top_types = sorted(reason_counts.items(), key=lambda x: (-x[1], x[0]))[:8]
    return {
        "window":window,"priority":priority,
        "incident_type":incident_type,
        "selected_incident_type":resolve_incident_type(incident_type),
        "records":records,"total_stored":stored,
        "dispatched_count":dispatched,"dispatch_flag_known":dispatch_known,
        "transported_count":transported,"transport_flag_known":transport_known,
        "neighborhoods_in_source":len(neighborhood_set),
        "record_quality":{
            "incident_type_coded_count":records-type_counts.get("Uncoded",0),
            "incident_type_uncoded_count":type_counts.get("Uncoded",0),
            "priority_coded_count":records-priority_counts.get("Unknown",0),
            "neighborhood_labeled_count":neighborhood_labeled_count,
            "dispatch_flag_known_count":dispatch_known,
            "transport_flag_known_count":transport_known,
        },
        "daily":[{"date":d,"count":date_counts[d]} for d in sorted(date_counts)],
        "daily_chart":chart_days,
        "daily_chart_excluded":partial_days,
        "daily_chart_note":chart_note,
        "hours":[{"hour":h,"count":hour_counts[h]} for h in range(24)],
        "priorities":[{"priority":p,"count":priority_counts[p]} for p in
                      sorted(priority_counts,key=lambda x:(x=="Unknown",x))],
        "incident_types":[{"type":name,"count":n} for name,n in top_types],
        "incident_reason_records":reason_total,
        "incident_type_excluded_count":records-reason_total,
        "incident_type_category_count":len(reason_counts),
        "incident_type_other_count":max(0,reason_total-sum(n for _,n in top_types)),
        "incident_type_uncoded_count":type_counts.get("Uncoded",0),
        "latest_call":iso(newest),"earliest_call":iso(earliest),
        "last_successful_sync":iso(last_success),
        "last_sync_failed":last_attempt=="failed",
        "source":"City of Cleveland (Ohio) CAD_EMS_Public",
        "source_item_id":SOURCE_ITEM_ID,
        "note":("Counts are Cleveland-published EMS records, not verified unique emergencies. "
                "Dispatch and transport fields are source flags, not measured response times. "
                "Incident types are classifications understood at dispatch."),
    }


def area_summary(*,window="30d",priority="all",incident_type="all",now=None,
                 start_date=None,end_date=None,known_neighborhoods=None):
    """Only source-provided, boundary-matched neighborhoods; suppress counts <11."""
    known = {name.strip().casefold():name for name in (known_neighborhoods or [])}
    area_counts = Counter()
    # Only publish a neighborhood-level category when its cell count meets
    # the same reporting threshold as the neighborhood total.
    area_types = defaultdict(Counter)
    total = 0
    unassigned = 0
    for row in _query_rows(window=window,priority=priority,incident_type=incident_type,now=now,
                           start_date=start_date,end_date=end_date):
        total += 1
        label = (row.neighborhood or "").strip()
        if label and label.casefold() in known:
            matched_name = known[label.casefold()]
            area_counts[matched_name] += 1
            area_types[matched_name][row.incident_type or "Uncoded"] += 1
        else:
            unassigned += 1
    mapped = sum(area_counts.values())
    allowed = []
    for name, count in sorted(area_counts.items(), key=lambda v: (-v[1], v[0])):
        if count < 11:
            continue
        top_name, top_count = area_types[name].most_common(1)[0]
        allowed.append({
            "name": name,
            "count": count,
            # A small category count is suppressed independently from the
            # larger neighborhood total; unknown is not inferred as zero.
            "top_incident_type": top_name if top_count >= 11 else None,
            "top_incident_type_count": top_count if top_count >= 11 else None,
        })
    return {
        "status":"ready" if allowed else ("suppressed" if mapped else "no_verified_geography"),
        "reporting_threshold":11,
        "mapped_records":mapped,
        "eligible_records":total,
        "unmapped_records":unassigned,
        "mapping_coverage_pct":round(100*mapped/total,1) if total else None,
        "areas":allowed,
        "note":("Source-provided Cleveland neighborhood labels matched to Cleveland GIS boundaries. "
                "Counts below 11 suppressed, including incident-type category cells. "
                "Differences in neighborhood naming are excluded rather than guessed; "
                "values are published rows, not unique incidents."),
    }


def bootstrap_if_needed(*, initial_days=400):
    """Additively initialize the Cleveland table only when it is empty.

    The legacy Virginia Beach table stays untouched. Repeated preview deploys
    should not fetch 400 days of records each time.
    """
    init_database()
    with SessionLocal() as db:
        stored = db.scalar(select(func.count(ClevelandRecord.object_id))) or 0
    if stored:
        print(f"Cleveland table already contains {stored:,} records; bootstrap skipped",flush=True)
        return {"already_stored":stored}
    return sync_data(days=initial_days)


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest="cmd",required=True)
    sync=sub.add_parser("sync",help="Import official Cleveland EMS source into separate table")
    boot=sub.add_parser("bootstrap",help="Import 400 days only if Cleveland table is empty")
    boot.add_argument("--days",type=int,default=400)
    sync.add_argument("--days",type=int,default=400)
    args=parser.parse_args()
    if args.cmd=="sync":
        print(sync_data(days=args.days),flush=True)
    if args.cmd=="bootstrap":
        print(bootstrap_if_needed(initial_days=args.days),flush=True)
