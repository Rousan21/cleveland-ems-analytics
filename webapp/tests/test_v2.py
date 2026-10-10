import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Set isolated DB before importing webapp modules.
TEST_DIR = tempfile.TemporaryDirectory()
os.environ['EMS_DATABASE_URL'] = f"sqlite:///{Path(TEST_DIR.name) / 'test.db'}"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, func
from db import EMSCall, EMSArea, SyncRun, SessionLocal, engine, init_database
from analytics import summarize, get_bounds
from ingest import fetch_pages, row_from_attributes, sync_data
from main import app


@pytest.fixture(autouse=True)
def clean_db():
    init_database()
    with engine.begin() as conn:
        conn.execute(delete(EMSArea))
        conn.execute(delete(EMSCall))
        conn.execute(delete(SyncRun))
    yield


def example_call(id=1, when=None, priority='2', call_delay=2, scene_delay=12):
    when = when or datetime.now(timezone.utc) - timedelta(hours=2)
    return EMSCall(object_id=id, priority=priority, call_time=when - timedelta(minutes=call_delay),
                   dispatch_time=when, scene_time=when + timedelta(minutes=scene_delay-call_delay),
                   block_location='REDACTED', city='CLEVELAND')


def test_empty_home_and_api():
    with TestClient(app) as client:
        assert client.get('/').status_code == 200
        response = client.get('/api/summary')
        assert response.status_code == 200
        assert response.json()['records'] == 0
        assert response.json()['last_successful_sync'] is None
        assert client.get('/health').json() == {'status': 'ok'}
        assert 'REDACTED' not in response.text


def test_time_windows_and_priorities():
    current = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.add_all([example_call(1, current-timedelta(hours=3), '1'),
                    example_call(2, current-timedelta(days=6), '2'),
                    example_call(3, current-timedelta(days=40), '3')])
        db.commit()
    with TestClient(app) as client:
        assert client.get('/api/summary?window=24h').json()['records'] == 1
        assert client.get('/api/summary?window=7d').json()['records'] == 2
        assert client.get('/api/summary?window=90d').json()['records'] == 3
        assert client.get('/api/summary?window=all').json()['records'] == 3
        priority = client.get('/api/summary?window=90d&priority=1').json()
        assert priority['records'] == 1
        assert priority['median_call_to_dispatch_min'] == 2.0
        assert priority['median_call_to_scene_min'] == 12.0
        assert client.get('/api/summary?priority=9').status_code == 422
        assert client.get('/api/summary?window=garbage').status_code == 422
        assert client.get('/api/summary?window=custom&start=2026-12-01&end=2026-01-01').status_code == 422


def test_custom_boundaries_across_daylight_savings():
    start, end = get_bounds('custom', '2026-11-01', '2026-11-01')
    # Local fall-back day in Cleveland contains 25 hours.
    assert (end-start).total_seconds() == 25*3600


class FakeResponse:
    def __init__(self, payload): self.payload = payload
    def raise_for_status(self): pass
    def json(self): return self.payload


class FakeArcGIS:
    def __init__(self): self.calls = 0
    def get(self, url, params, timeout):
        self.calls += 1
        assert params['returnGeometry'] == 'false'
        assert 'Block_Location' in params['outFields']
        if self.calls == 1:
            return FakeResponse({'features': [{'attributes': {'OBJECTID': 11, 'Call_Priority': '1', 'Call_Date_Time': 1000,
                                    'Dispatch_Date_Time': 61000, 'On_Scene_Date_Time': 121000,
                                    'Block_Location': 'SOME BLOCK', 'City': 'Cleveland'}}]})
        return FakeResponse({'features': []})


def test_import_idempotent_and_private():
    fake = FakeArcGIS()
    assert sync_data(days=None, session=fake) == 1
    assert sync_data(days=None, session=FakeArcGIS()) == 1
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(EMSCall)) == 1
        assert db.scalar(select(func.count()).select_from(SyncRun)) == 2
    with TestClient(app) as client:
        body = client.get('/api/summary?window=all').text
        assert 'SOME BLOCK' not in body
        assert 'last_successful_sync' in body


def test_reject_duplicate_paging():
    class FaultyArcGIS:
        def get(self, url, params, timeout):
            return FakeResponse({'features': [{'attributes': {'OBJECTID': 1}}, {'attributes': {'OBJECTID': 1}}]})
    with pytest.raises(RuntimeError, match='unordered or repeated'):
        list(fetch_pages(days=None, session=FaultyArcGIS()))


def test_verified_neighborhood_aggregation_and_small_counts():
    from db import EMSArea
    from geography import get_area_summary
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.add_all([example_call(i, now-timedelta(hours=3)) for i in range(1,16)])
        db.add_all([EMSArea(object_id=i, neighborhood=('Ohio City' if i <= 12 else 'Tremont'),
                            source_note='Reviewed joined geographic source') for i in range(1,16)])
        db.commit()
    with TestClient(app) as client:
        areas = client.get('/api/areas?window=24h').json()
    assert areas['status'] == 'ready'
    assert areas['mapped_records'] == 15
    assert areas['areas'] == [{'name':'Ohio City','count':12}]
    assert 'Tremont' not in str(areas['areas'])
    assert 'REDACTED' not in str(areas)


def test_boundary_geojson_sanitization(monkeypatch, tmp_path):
    import geography
    payload = { 'type': 'FeatureCollection', 'features': [
        {'type':'Feature','properties': {'Neighborhood': f'Area {i}', 'sensitive':'do-not-send'},
         'geometry': {'type':'Polygon','coordinates':[[[-81.7,41.5],[-81.6,41.5],[-81.6,41.4],[-81.7,41.5]]]}}
        for i in range(12)
    ]}
    class DummyClient:
        def get(self, url, params, timeout):
            assert params['f'] == 'geojson'
            assert params['returnGeometry'] == 'true'
            return FakeResponse(payload)
    monkeypatch.setattr(geography,'CACHE_FILE',tmp_path/'test-neighborhoods.geojson')
    result = geography.get_boundaries(client=DummyClient())
    assert len(result['features']) == 12
    assert result['features'][0]['properties'] == {'name': 'Area 0'}
    assert (tmp_path/'test-neighborhoods.geojson').exists()
    assert geography.get_boundaries()['features'][0]['properties']['name'] == 'Area 0'


def test_home_uses_vector_boundary_map_no_tile_layer():
    js = (Path(__file__).resolve().parents[1] / 'static' / 'dashboard.js').read_text()
    assert "L.geoJSON" in js
    assert 'L.tileLayer' not in js
    assert 'openstreetmap.org' not in js
