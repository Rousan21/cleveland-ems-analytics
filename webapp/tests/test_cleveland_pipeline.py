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
    assert summary["record_quality"]["neighborhood_labeled_count"]==3
    assert summary["record_quality"]["incident_type_coded_count"]==3
    assert summary["record_quality"]["dispatch_flag_known_count"]==3
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
    assert result["areas"]==[{
        "name":"Ohio City","count":12,
        "top_incident_type":"Medical","top_incident_type_count":12,
    }]
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


def test_partial_rolling_window_dates_are_excluded_from_comparative_chart():
    """A four-hour first day and eight-row current day must not look like drops."""
    fixed=datetime(2026,11,15,22,0,tzinfo=timezone.utc)
    from cleveland_pipeline import select_comparable_calendar_days
    from datetime import timedelta

    start=fixed-timedelta(days=30)
    counts={
        "2026-10-16":68,       # first date includes only local evening
        "2026-10-17":291,
        "2026-11-14":289,
        "2026-11-15":8,        # newest local date incomplete
    }
    plotted, dropped, note=select_comparable_calendar_days(
        counts, window="30d",start=start,end=fixed
    )
    assert [r["date"] for r in plotted]==["2026-10-17","2026-11-14"]
    assert [r["date"] for r in dropped]==["2026-10-16","2026-11-15"]
    assert "complete Cleveland-local" in note
    assert sum(r["count"] for r in plotted)==580
    assert sum(counts.values())==656  # total still reflects full selection


def test_rolling_past_day_is_not_presented_as_full_calendar_comparison():
    from cleveland_pipeline import select_comparable_calendar_days
    fixed=datetime(2026,11,15,22,0,tzinfo=timezone.utc)
    data={"2026-11-14":12,"2026-11-15":25}
    displayed,dropped,note=select_comparable_calendar_days(
        data,window="24h",start=fixed-timedelta(days=1),end=fixed
    )
    assert len(displayed)==2
    assert dropped==[]
    assert "partial" in note.lower()


def test_neighborhood_top_incident_type_is_suppressed_below_11():
    now=datetime.now(timezone.utc)-timedelta(hours=4)
    with SessionLocal() as db:
        db.add_all([
            ClevelandRecord(object_id=i,incident_time=now,neighborhood="Ohio City",
                            priority="3",incident_type="Sick Person" if i<=10 else "Falls",
                            dispatch_flag="true",transport_flag="false")
            for i in range(1,16)
        ])
        db.commit()
    result=area_summary(window="7d",priority="3",known_neighborhoods=["Ohio City"])
    assert result["areas"] == [{
        "name":"Ohio City","count":15,
        "top_incident_type":None,"top_incident_type_count":None
    }]
    assert "Sick Person" not in str(result["areas"])


def test_citywide_incident_type_distribution_has_clear_denominator():
    """Unambiguous published-row denominator for type ranking percentages."""
    now=datetime.now(timezone.utc)-timedelta(hours=2)
    with SessionLocal() as db:
        db.add_all([
            ClevelandRecord(object_id=i,incident_time=now,neighborhood="Downtown",
                           priority="2",incident_type=("SICK PERSON" if i<=16 else "FALLS"),
                           dispatch_flag="true",transport_flag="true")
            for i in range(1,22)
        ])
        db.commit()
    result=summarize(window="7d",priority="2")
    assert result["records"]==21
    assert result["incident_types"]==[
        {"type":"SICK PERSON","count":16},{"type":"FALLS","count":5}
    ]
    assert result["incident_type_category_count"]==2
    assert result["incident_type_other_count"]==0
    assert result["incident_type_uncoded_count"]==0
    assert result["record_quality"]["incident_type_coded_count"]==21
    assert result["record_quality"]["priority_coded_count"]==21
    assert result["record_quality"]["transport_flag_known_count"]==21
    assert result["transported_count"]==21
    assert result["transport_flag_known"]==21


def test_incident_type_filter_changes_citywide_and_neighborhood_totals():
    from cleveland_pipeline import common_incident_types
    now = datetime.now(timezone.utc) - timedelta(hours=3)
    with SessionLocal() as db:
        db.add_all([
            ClevelandRecord(
                object_id=i, incident_time=now,
                neighborhood="Ohio City" if i<=18 else "Tremont",
                priority="2",
                incident_type="BREATHING PROBLEMS" if i<=24 else "SICK PERSON",
                dispatch_flag="true", transport_flag="false"
            ) for i in range(1,43)
        ])
        db.commit()
    choices=common_incident_types()
    assert len(choices)==2
    breathing=next(x["id"] for x in choices if x["label"]=="BREATHING PROBLEMS")
    selected=summarize(window="7d", incident_type=breathing)
    assert selected["records"]==24
    assert selected["selected_incident_type"]=="BREATHING PROBLEMS"
    assert selected["incident_types"]==[{"type":"BREATHING PROBLEMS","count":24}]
    geographic=area_summary(window="7d",incident_type=breathing,known_neighborhoods=["Ohio City","Tremont"])
    assert geographic["eligible_records"]==24
    assert geographic["mapped_records"]==24
    assert [r["name"] for r in geographic["areas"]]==["Ohio City"]
    with pytest.raises(ValueError,match="Unknown Cleveland incident"):
        summarize(window="7d",incident_type="not_an_official_category")
