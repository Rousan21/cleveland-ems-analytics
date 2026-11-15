"""Public station GIS context: no incident records and no inferred coverage."""
from geography import get_ems_stations


class Response:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return None

    def json(self):
        return self.content


class FakeStationClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append((url, params, timeout))
        return Response(self.payload)


def test_official_station_geometries_are_reduced_to_public_facilities():
    client = FakeStationClient({
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "EMS_STATION": "Station A", "ADDRESS": "PUBLIC FACILITY",
                    "Patient": "secret",
                    "IncidentID": 222222,
                },
                "geometry": {"type": "Point", "coordinates": [-81.70, 41.50]},
            },
            {
                "type": "Feature",
                "properties": {"EMS_STATION": "Station A", "ADDRESS": "PUBLIC FACILITY"},
                "geometry": {"type": "Point", "coordinates": [-81.70, 41.50]},
            },
            {
                "type": "Feature",
                "properties": {"EMS_STATION": "Outside metro", "ADDRESS": "EXCLUDE"},
                "geometry": {"type": "Point", "coordinates": [-73.0, 40.0]},
            },
            {
                "type": "Feature",
                "properties": {"EMS_STATION": "Invalid feature"},
                "geometry": {"type": "Polygon", "coordinates": []},
            },
        ]
    })
    result = get_ems_stations(client=client)
    assert result["status"] == "ready"
    assert result["stations"] == [{
        "name": "Station A", "address": "PUBLIC FACILITY",
        "lat": 41.50, "lon": -81.70,
    }]
    assert "secret" not in str(result)
    assert "222222" not in str(result)
    _, params, _ = client.calls[0]
    assert params["outFields"] == "EMS_STATION,ADDRESS"
    assert params["outSR"] == 4326
    assert params["returnGeometry"] == "true"


def test_station_service_failures_never_publish_invented_markers():
    result = get_ems_stations(client=FakeStationClient({"error":{"message":"offline"}}))
    assert result["status"] == "unavailable"
    assert result["stations"] == []
