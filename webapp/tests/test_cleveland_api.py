"""Public Cleveland-only API contract and geographic aggregation tests."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from db import ClevelandRecord, SessionLocal, engine, init_database
from main import app


@pytest.fixture(autouse=True)
def clean_cleveland():
    init_database()
    with engine.begin() as connection:
        connection.execute(delete(ClevelandRecord))
    yield


def test_new_api_reports_only_correct_cleveland_source():
    with TestClient(app) as client:
        empty=client.get("/api/summary").json()
        assert empty["source_item_id"]=="d5d71757cc73400d843c98bcb46e46b6"
        assert empty["records"]==0
        assert "median_call_to_dispatch_min" not in empty
        assert "Virginia Beach" not in str(empty)
        assert client.get("/api/source").json()["name"].startswith("City of Cleveland")


def test_new_api_rejects_invalid_priority_and_custom_range():
    with TestClient(app) as client:
        assert client.get("/api/summary?priority=8").status_code==422
        assert client.get("/api/summary?window=bogus").status_code==422
        assert client.get("/api/summary?window=custom&start=2026-12-01&end=2026-01-01").status_code==422


def test_new_api_neighborhood_counts_and_privacy(monkeypatch):
    import main
    now=datetime.now(timezone.utc)-timedelta(hours=3)
    with SessionLocal() as db:
        db.add_all([
            ClevelandRecord(
                object_id=i,incident_time=now,neighborhood=("Ohio City" if i<=13 else "Tremont"),
                priority="3",incident_type="Medical",dispatch_flag="true",transport_flag="false"
            ) for i in range(1,17)
        ])
        db.commit()
    monkeypatch.setattr(main,"get_boundaries",lambda:{
        "type":"FeatureCollection",
        "features":[{"properties":{"name":"Ohio City"}},
                    {"properties":{"name":"Tremont"}}]})
    with TestClient(app) as client:
        result=client.get("/api/areas?window=7d&priority=3")
        assert result.status_code==200
        data=result.json()
        assert data["eligible_records"]==16
        assert data["mapped_records"]==16
        assert data["areas"]==[{
            "name":"Ohio City","count":13,
            "top_incident_type":"Medical","top_incident_type_count":13
        }]
        summary=client.get("/api/summary?window=7d&priority=3").json()
        assert summary["records"]==16
        assert summary["dispatched_count"]==16
        assert summary["transport_flag_known"]==16
        assert "ObjectId" not in str(result.json())


def test_api_incident_type_selector_filters_cleveland_records(monkeypatch):
    import main
    now=datetime.now(timezone.utc)-timedelta(hours=1)
    with SessionLocal() as db:
        db.add_all([
            ClevelandRecord(object_id=i,incident_time=now,neighborhood="Ohio City",
                priority="2",incident_type="SICK PERSON" if i<=23 else "FALLS",
                dispatch_flag="true",transport_flag="false")
            for i in range(1,41)
        ])
        db.commit()
    monkeypatch.setattr(main,"get_boundaries",lambda:{
        "type":"FeatureCollection","features":[{"properties":{"name":"Ohio City"}}]})
    with TestClient(app) as client:
        choices=client.get("/api/incident-types").json()["types"]
        assert {x["label"] for x in choices}=={"SICK PERSON","FALLS"}
        selected=next(x["id"] for x in choices if x["label"]=="SICK PERSON")
        data=client.get("/api/summary",params={"window":"7d","incident_type":selected})
        assert data.status_code==200
        assert data.json()["records"]==23
        assert data.json()["selected_incident_type"]=="SICK PERSON"
        area=client.get("/api/areas",params={"window":"7d","incident_type":selected})
        assert area.status_code==200
        assert area.json()["eligible_records"]==23
        assert area.json()["areas"][0]["count"]==23
        assert client.get("/api/summary?incident_type=bad").status_code==422
