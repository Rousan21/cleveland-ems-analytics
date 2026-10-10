"""Import public ArcGIS EMS data using paginated, idempotent upserts.

Run manually or from an external scheduler. No patient-level locations are published.
"""
import argparse
from datetime import datetime, timedelta, timezone

import requests
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from db import EMSCall, SyncRun, SessionLocal, engine, init_database

API_URL = ("https://services2.arcgis.com/CyVvlIiUfRBmMQuu/arcgis/rest/services/"
           "EMS_Calls_for_Service2/FeatureServer/0/query")
FIELDS = "OBJECTID,Call_Priority,Call_Date_Time,Dispatch_Date_Time,On_Scene_Date_Time,Block_Location,City"
PAGE_SIZE = 1000


def parse_epoch_ms(value):
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def row_from_attributes(a):
    return {
        "object_id": int(a["OBJECTID"]),
        "priority": a.get("Call_Priority"),
        "call_time": parse_epoch_ms(a.get("Call_Date_Time")),
        "dispatch_time": parse_epoch_ms(a.get("Dispatch_Date_Time")),
        "scene_time": parse_epoch_ms(a.get("On_Scene_Date_Time")),
        "block_location": a.get("Block_Location"),
        "city": a.get("City"),
    }


def fetch_pages(*, days: int | None = 90, session=None):
    """Keyset pagination prevents skipped records from large result offsets.

    ArcGIS TIMESTAMP SQL filtering needs validation when the provider updates its API.
    """
    client = session or requests.Session()
    last_id = -1
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)) if days is not None else None
    while True:
        conditions = [f"OBJECTID > {last_id}"]
        if cutoff:
            conditions.append(f"Dispatch_Date_Time >= TIMESTAMP '{cutoff:%Y-%m-%d %H:%M:%S}'")
        params = {
            "where": " AND ".join(conditions),
            "outFields": FIELDS,
            "returnGeometry": "false",
            "orderByFields": "OBJECTID ASC",
            "resultRecordCount": PAGE_SIZE,
            "f": "json",
        }
        response = client.get(API_URL, params=params, timeout=45)
        response.raise_for_status()
        payload = response.json()
        if payload.get("error"):
            raise RuntimeError(f"ArcGIS query rejected: {payload['error']}")
        features = payload.get("features", [])
        if not features:
            return
        rows = [row_from_attributes(item["attributes"]) for item in features]
        if rows[0]["object_id"] <= last_id or any(
            rows[i]["object_id"] >= rows[i + 1]["object_id"] for i in range(len(rows) - 1)
        ):
            raise RuntimeError("ArcGIS returned unordered or repeated OBJECTIDs; import stopped")
        yield rows
        last_id = rows[-1]["object_id"]
        if len(rows) < PAGE_SIZE and not payload.get("exceededTransferLimit", False):
            return


def upsert_rows(connection, rows):
    """Batch statements to respect SQLite parameter limits on older systems."""
    for start in range(0, len(rows), 100):
        _upsert_batch(connection, rows[start:start + 100])


def _upsert_batch(connection, rows):
    table = EMSCall.__table__
    dialect = connection.dialect.name
    if dialect == "postgresql":
        statement = pg_insert(table).values(rows)
    elif dialect == "sqlite":
        statement = sqlite_insert(table).values(rows)
    else:
        raise RuntimeError(f"Unsupported database dialect for upserts: {dialect}")
    update = {c.name: statement.excluded[c.name] for c in table.columns if c.name != "object_id"}
    connection.execute(statement.on_conflict_do_update(index_elements=["object_id"], set_=update))


def sync_data(*, days: int | None = 90, session=None):
    init_database()
    processed = 0
    try:
        for rows in fetch_pages(days=days, session=session):
            with engine.begin() as connection:
                upsert_rows(connection, rows)
            processed += len(rows)
            print(f"Synced {processed:,} source rows", flush=True)
    except Exception as error:
        with SessionLocal() as db:
            db.add(SyncRun(finished_at=datetime.now(timezone.utc), record_count=processed,
                           status="failed", detail=str(error)[:500]))
            db.commit()
        raise
    with SessionLocal() as db:
        db.add(SyncRun(finished_at=datetime.now(timezone.utc), record_count=processed, status="success"))
        db.commit()
    return processed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import Cleveland EMS public data")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--days", type=int, default=90, help="Refresh a recent date window (default 90)")
    group.add_argument("--all", action="store_true", help="Backfill entire available history (may take time)")
    args = parser.parse_args()
    if args.days is not None and args.days <= 0:
        parser.error("--days must be positive")
    print(f"Finished: {sync_data(days=None if args.all else args.days):,} records synchronized")
