"""Static deployment contract tests. No live Neon or ArcGIS access required."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def test_build_static_site_preserves_filters_and_privacy(tmp_path, monkeypatch):
    import export_static
    calls = []

    def fake_summary(*, window, priority, now):
        calls.append(("summary", window, priority))
        return {
            "window": window, "priority": priority, "total_stored": 20,
            "records": 12, "daily": [], "hours": [], "priorities": [],
            "median_call_to_dispatch_min": 2.0,
            "median_call_to_scene_min": 12.0,
            "last_successful_sync": now.isoformat(),
            "block_location": None,  # Not present in the real API output.
        }

    def safe_summary(**kwargs):
        data = fake_summary(**kwargs)
        data.pop("block_location")
        return data

    def fake_areas(*, window, priority, now):
        calls.append(("areas", window, priority))
        return {"status": "no_verified_geography", "areas": []}

    monkeypatch.setattr(export_static, "summarize", safe_summary)
    monkeypatch.setattr(export_static, "get_area_summary", fake_areas)
    monkeypatch.setattr(export_static, "publication_history", lambda **kwargs: {"status":"collecting","days":[]})
    monkeypatch.setattr(export_static, "get_boundaries", lambda: {
        "type": "FeatureCollection", "features": []
    })

    output = export_static.build_site(tmp_path / "site")
    assert 'data-static-site="true"' in (output / "index.html").read_text()
    assert (output / "static" / "dashboard.js").exists()
    assert (output / "static" / "v3.css").exists()
    assert (output / "static" / "v4.css").exists()
    assert (output / "static" / "v4.js").exists()
    assert (output / "api" / "publication-history.json").exists()
    assert 'id="insight-hour"' in (output / "index.html").read_text()
    assert 'id="reliability"' in (output / "index.html").read_text()
    assert 'id="neighborhood-select"' in (output / "index.html").read_text()
    assert 'Adam Al-Rousan' in (output / "index.html").read_text()
    assert 'id="download-daily"' in (output / "index.html").read_text()
    assert len([c for c in calls if c[0] == "summary"]) == 24
    assert len([c for c in calls if c[0] == "areas"]) == 24
    assert (output / "api" / "summary" / "all" / "3.json").exists()
    assert (output / "api" / "areas" / "7d" / "1.json").exists()
    assert not (output / "api" / "summary" / "custom").exists()
    data = json.loads((output / "api" / "summary" / "30d" / "all.json").read_text())
    assert data["records"] == 12
    assert data["snapshot_generated_at"]
    assert "block_location" not in data
    assert "EMS_DATABASE_URL" not in (output / "index.html").read_text()

    with pytest.raises(ValueError, match="must be empty"):
        export_static.build_site(output)


def test_cloudflare_page_origin_can_request_custom_aggregates():
    from main import app
    for origin in (
        "https://cleveland-ems-explorer.pages.dev",
        "https://preview.cleveland-ems-explorer.pages.dev",
    ):
        with TestClient(app) as client:
            response = client.get("/health", headers={"Origin": origin})
            assert response.headers.get("access-control-allow-origin") == origin
            assert response.json() == {"status": "ok"}

    with TestClient(app) as client:
        response = client.get("/health", headers={"Origin": "https://untrusted.example"})
        assert "access-control-allow-origin" not in response.headers
