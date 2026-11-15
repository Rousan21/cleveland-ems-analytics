"""Cleveland-only static export: source provenance, geographic coverage and privacy."""
import json

import pytest
from fastapi.testclient import TestClient


def test_static_build_contains_only_cleveland_source_and_aggregate_geography(tmp_path, monkeypatch):
    import export_static

    calls=[]
    def fake_summary(*, window, priority, now):
        calls.append(("summary",window,priority))
        return {
            "source_item_id":export_static.SOURCE_ITEM_ID,
            "source":"City of Cleveland (Ohio) CAD_EMS_Public",
            "window":window,"priority":priority,"records":16,"total_stored":20,
            "daily":[{"date":"2026-11-10","count":16}],
            "hours":[{"hour":10,"count":16}],"priorities":[{"priority":"2","count":16}],
            "incident_types":[{"type":"Medical","count":16}],
            "incident_type_category_count":1,"incident_type_other_count":0,
            "incident_type_uncoded_count":0,
            "dispatched_count":12,"dispatch_flag_known":16,
            "transported_count":8,"transport_flag_known":16,
            "neighborhoods_in_source":1,
            "latest_call":now.isoformat(),"earliest_call":now.isoformat(),
            "last_successful_sync":now.isoformat(),
        }

    def fake_areas(*,window,priority,now,known_neighborhoods):
        calls.append(("area",window,priority))
        assert "Ohio City" in known_neighborhoods
        return {"status":"ready","eligible_records":16,"mapped_records":16,
                "mapping_coverage_pct":100.0,
                "areas":[{"name":"Ohio City","count":16}]}

    def fake_boundaries():
        return {"type":"FeatureCollection","features":[
            {"type":"Feature","properties":{"name":f"Area {i}"}, "geometry": {
                "type":"Polygon","coordinates":[]}} for i in range(20)] + [
            {"type":"Feature","properties":{"name":"Ohio City"}, "geometry":{
                "type":"Polygon","coordinates":[]}}
        ]}

    monkeypatch.setattr(export_static,"summarize",fake_summary)
    monkeypatch.setattr(export_static,"area_summary",fake_areas)
    monkeypatch.setattr(export_static,"get_boundaries",fake_boundaries)

    output=export_static.build_site(tmp_path/"site")
    html=(output/"index.html").read_text()
    assert 'data-static-site="true"' in html
    assert 'Adam Al-Rousan' in html
    assert 'id="neighborhood-select"' in html
    assert 'id="geo-mapped-count"' in html
    assert 'id="transport-share"' in html
    assert 'id="reason-rankings"' in html
    assert 'id="reason-coverage"' in html
    assert 'id="priority-chart"' not in html
    assert (output/"static"/"v6.css").exists()
    assert (output/"static"/"v6.js").exists()
    assert (output/"api"/"areas"/"7d"/"7.json").exists()
    assert len([x for x in calls if x[0]=="summary"]) == 48
    assert len([x for x in calls if x[0]=="area"]) == 48

    summary=json.loads((output/"api"/"summary"/"30d"/"all.json").read_text())
    assert summary["source_item_id"] == export_static.SOURCE_ITEM_ID
    assert summary["records"] == 16
    assert summary["snapshot_generated_at"]
    assert "block_location" not in str(summary).lower()
    assert "patient" not in str(summary).lower()
    assert not (output/"api"/"ems-stations.json").exists()
    assert not (output/"api"/"summary"/"custom").exists()
    assert "EMS_DATABASE_URL" not in html
    with pytest.raises(ValueError,match="must be empty"):
        export_static.build_site(output)


def test_static_export_refuses_wrong_source(tmp_path,monkeypatch):
    import export_static
    monkeypatch.setattr(export_static,"get_boundaries",lambda:{
        "type":"FeatureCollection","features":[
            {"properties":{"name":f"Area {i}"}} for i in range(21)]})
    monkeypatch.setattr(export_static,"summarize",lambda **kwargs:{
        "records":90,"total_stored":400,
        "source_item_id":"virginia-beach",
    })
    with pytest.raises(RuntimeError,match="provenance mismatch"):
        export_static.build_site(tmp_path/"site")


def test_cloudflare_page_origin_can_request_public_aggregate_api():
    from main import app
    for origin in (
        "https://cleveland-ems-explorer.pages.dev",
        "https://preview.cleveland-ems-explorer.pages.dev",
    ):
        with TestClient(app) as client:
            response=client.get("/health",headers={"Origin":origin})
            assert response.headers.get("access-control-allow-origin")==origin
    with TestClient(app) as client:
        response=client.get("/health",headers={"Origin":"https://untrusted.example"})
        assert "access-control-allow-origin" not in response.headers
