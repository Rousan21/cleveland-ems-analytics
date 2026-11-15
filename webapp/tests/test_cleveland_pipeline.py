"""Cleveland, Ohio provenance and neighborhood-count tests. Offline-only fixtures."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, func, select

from db import ClevelandRecord, ClevelandSyncRun, EMSCall, SessionLocal, engine, init_database
from cleveland_pipeline import (
    EXPECTED_FIELDS, SOURCE_ITEM_ID, area_summary, fetch_pages, row_from_attrs,
    summarize, sync_data,
)


@pytest.fixture(autouse=True)
def clear_cleveland_rows():
    init_database()
    with engine.begin() as connection:
        connection.execute(delete(ClevelandRecord))
        connection.execute(delete(ClevelandSyncRun))
    yield


def fake_record(object_id, when, city="Cleveland", neighborhood="Ohio City",
                priority="2", dispatch="true", transport="false", incident_type="Medical"):
    return {
        "ObjectId":object_id,
        "IncidentDate":int(when.timestamp()*1000),
        "city":city,"neighborhood":neighborhood,
        "CurrentPriorityKey":priority,
        "IncidentTypeDescription":incident_type,
        "isDispatch":dispatch,"isTransport":transport,
        "census_tract":"39035123400",
        "IncidentNumber":"PRIVATE-INCIDENT-IDENTIFIER",
        "recordserialno":"PRIVATE-PATIENT-SERIAL",
        "fulladdr":"PRIVATE-HOME-ADDRESS",
    }


def test_mismatched_city_rows_rejected_and_identifiers_never_saved():
    now=datetime.now(timezone.utc)
    virginia=fake_record(10,now,city="Virginia Beach")
    assert row_from_attrs(virginia) is None
    record=row_from_attrs(fake_record(11,now))
    assert record["neighborhood"]=="Ohio City"
    assert record["incident_time"]==now.replace(microsecond=(now.microsecond // 1000) * 1000)
    assert record["dispatch_flag"]=="true"
    assert record["transport_flag"]=="false"
    assert "PRIVATE" not in str(record)
    assert "IncidentNumber" not in str(record)
    assert set(record)=={
        "object_id","incident_time","neighborhood","priority",
        "incident_type","dispatch_flag","transport_flag","tract"
    }


class FakeResponse:
    def __init__(self,payload):self.payload=payload
    def raise_for_status(self):pass
    def json(self):return self.payload


class FakeSource:
    def __init__(self,rows):
        self.rows=rows
        self.queries=[]
    def get(self,url,params,timeout):
        self.queries.append((url,params))
        if url.endswith("/query"):
            found=self.rows if len([q for q in self.queries if q[0].endswith("/query")])==1 else []
            return FakeResponse({"features":[{"attributes":r} for r in found]})
        return FakeResponse({
            "type":"Table",
            "fields":[{"name":f} for f in EXPECTED_FIELDS],
        })


def test_cleveland_import_idempotent_and_does_not_read_legacy_table():
    when=datetime.now(timezone.utc)-timedelta(hours=8)
    source=FakeSource([fake_record(1,when),fake_record(2,when,city="Virginia Beach"),
                       fake_record(3,when,priority="5",neighborhood="Tremont"),
                       fake_record(4,when,priority="2",neighborhood="Ohio City")])
    result=sync_data(days=30,session=source)
    assert result["source_rows_seen"]==4
    assert result["cleveland_rows_upserted"]==3
    assert len(source.queries)==2
    assert "ObjectId" in source.queries[1][1]["outFields"]
    assert "EMS_Call_Number" not in source.queries[1][1]["outFields"]
    sync_data(days=30,session=FakeSource(source.rows))
    with SessionLocal() as db:
        assert db.scalar(select(func.count(ClevelandRecord.object_id)))==3
        assert db.scalar(select(func.count(EMSCall.object_id)))==0
        assert db.scalar(select(func.count(ClevelandSyncRun.id)))==2
    summary=summarize(window="7d")
    assert summary["records"]==3
    assert summary["source_item_id"]==SOURCE_ITEM_ID
    assert summary["dispatch_flag_known"]==3
    assert summary["transported_count"]==0
    assert summary["neighborhoods_in_source"]==2
    assert "PRIVATE" not in str(summary)
    assert "Virginia Beach" not in str(summary)


def test_neighborhood_ranking_and_privacy_threshold():
    now=datetime.now(timezone.utc)-timedelta(hours=4)
    with SessionLocal() as db:
        rows=[]
        for i in range(1,17):
            rows.append(ClevelandRecord(
                object_id=i,incident_time=now,neighborhood="Ohio City" if i<=12 else "Tremont",
                priority="2",incident_type="Medical",dispatch_flag="true",transport_flag="false"
            ))
        rows.append(ClevelandRecord(
            object_id=17,incident_time=now,neighborhood="Unmatched Other",
            priority="2",incident_type="Medical",dispatch_flag="true",transport_flag="false"
        ))
        db.add_all(rows)
        db.commit()
    result=area_summary(window="7d",
        known_neighborhoods=["Ohio City","Tremont","Downtown"])
    assert result["status"]=="ready"
    assert result["eligible_records"]==17
    assert result["mapped_records"]==16
    assert result["unmapped_records"]==1
    assert result["areas"]==[{"name":"Ohio City","count":12}]
    assert "Tremont" not in str(result["areas"])
    assert result["mapping_coverage_pct"]==94.1


def test_rejects_non_cleveland_source_majority():
    now=datetime.now(timezone.utc)-timedelta(hours=3)
    source=FakeSource([fake_record(1,now,city="Virginia Beach"),
                       fake_record(2,now,city="Virginia Beach"),
                       fake_record(3,now,city="Cleveland")])
    with pytest.raises(RuntimeError,match="75%"):
        sync_data(days=30,session=source)


def test_source_date_bounds_reject_bad_priority():
    with pytest.raises(ValueError,match="Unknown Cleveland"):
        summarize(window="7d",priority="9")


def test_source_contract_fails_if_required_field_disappears():
    class WrongSchema(FakeSource):
        def get(self,url,params,timeout):
            if not url.endswith("/query"):
                return FakeResponse({"type":"Table","fields":[{"name":"Bogus"}]})
            return super().get(url,params,timeout)
    with pytest.raises(RuntimeError,match="schema changed"):
        sync_data(days=30,session=WrongSchema([]))
