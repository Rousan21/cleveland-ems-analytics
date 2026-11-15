"""Read-only public-source sanity audit. Never prints incident numbers or addresses."""
from collections import Counter
from datetime import datetime, timezone

import requests

SOURCE = "https://services3.arcgis.com/dty2kHktVXHrqO8i/ArcGIS/rest/services/data/FeatureServer/0"
FIELD_NAMES = ("ObjectId", "IncidentDate", "neighborhood", "city", "CurrentPriorityKey",
               "IncidentTypeDescription", "isDispatch", "isTransport")


def audit():
    session = requests.Session()
    meta = session.get(SOURCE, params={"f": "json"}, timeout=35)
    meta.raise_for_status()
    layer = meta.json()
    names = {f["name"] for f in layer.get("fields", [])}
    assert set(FIELD_NAMES) <= names, f"Source missing required fields: {set(FIELD_NAMES)-names}"
    assert layer.get("type") == "Table", "Expected City of Cleveland published EMS table"
    print(f"Official Cleveland EMS source schema validated: {len(names)} fields; date field IncidentDate")
    for key in ("CurrentPriorityKey", "IncidentTypeDescription", "isTransport", "isDispatch"):
        definition = next((field for field in layer.get("fields", []) if field.get("name") == key), None)
        if definition:
            domain = definition.get("domain") or {}
            print(
                f"PUBLIC FIELD DEFINITION {key}: "
                f"alias={definition.get('alias')!r}; "
                f"field_type={definition.get('type')!r}; "
                f"description={definition.get('description')!r}; "
                f"coded_domain={domain.get('codedValues')!r}",
                flush=True
            )

    q = session.get(SOURCE+"/query",params={
        "where":"1=1", "returnCountOnly":"true", "f":"json"
    },timeout=35)
    q.raise_for_status()
    total=q.json()
    assert "count" in total, total.get("error")
    print(f"Public source total rows (not unique incidents): {total['count']:,}")
    recent=session.get(SOURCE+"/query",params={
        "where":"IncidentDate >= TIMESTAMP '2026-09-01 00:00:00'",
        "returnCountOnly":"true", "f":"json",
    },timeout=35)
    recent.raise_for_status()
    print("Records since 2026-09-01:",recent.json().get("count","unavailable"))
    sample=session.get(SOURCE+"/query",params={
        "where":"1=1", "outFields":",".join(FIELD_NAMES), "returnGeometry":"false",
        "orderByFields":"IncidentDate DESC, ObjectId DESC", "resultRecordCount":250, "f":"json"
    },timeout=45)
    sample.raise_for_status()
    data=sample.json()
    assert not data.get("error"),data.get("error")
    attrs=[r["attributes"] for r in data.get("features",[])]
    if not attrs: raise RuntimeError("No public Cleveland records in sample")
    print(f"Most recent dated sample: {len(attrs)} source rows; timestamp sample latest UTC: "
          f"{max(datetime.fromtimestamp(row['IncidentDate']/1000,tz=timezone.utc) for row in attrs if row.get('IncidentDate')):%Y-%m-%d}")
    for key in ["city", "CurrentPriorityKey", "isDispatch", "isTransport"]:
        print(f"{key}: {Counter(str(row.get(key)) for row in attrs).most_common(12)}")
    neighborhoods=Counter(str(row.get("neighborhood")) for row in attrs)
    print(f"Neighborhoods in sample: {len(neighborhoods)} distinct, "
          f"nonempty={sum(v for k,v in neighborhoods.items() if k.lower() not in ('none','null',''))}")
    print(f"Incident types distinct in sample: "
          f"{len(set(str(row.get('IncidentTypeDescription')) for row in attrs))}")
    # NO incident numbers, patient addresses or source IDs in CI logs.


if __name__=="__main__":
    audit()
