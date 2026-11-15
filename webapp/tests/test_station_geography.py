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
                    "NAME": "Station A", "ADDRESS": "PUBLIC FACILITY",
                    "CITY":"CLEVELAND","STATE":"OH",
                    "Patient": "secret",
                    "IncidentID": 222222,
                },
                "geometry": {"type": "Point", "coordinates": [-81.70, 41.50]},
            },
            {
                "type": "Feature",
                "properties": {"NAME": "Station A", "ADDRESS": "PUBLIC FACILITY", "CITY":"CLEVELAND","STATE":"OH"},
                "geometry": {"type": "Point", "coordinates": [-81.70, 41.50]},
            },
            {
                "type": "Feature",
                "properties": {"NAME": "Outside metro", "ADDRESS": "EXCLUDE", "CITY":"CLEVELAND","STATE":"OH"},
                "geometry": {"type": "Point", "coordinates": [-73.0, 40.0]},
            },
            {
                "type": "Feature",
                "properties": {"NAME": "Invalid feature","CITY":"CLEVELAND","STATE":"OH"},
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
    assert params["outFields"] == "NAME,ADDRESS,CITY,STATE"
    assert params["f"] == "json"
    assert params["outSR"] == 4326
    assert params["returnGeometry"] == "true"


def test_station_service_failures_never_publish_invented_markers():
    result = get_ems_stations(client=FakeStationClient({"error":{"message":"offline"}}))
    assert result["status"] == "unavailable"
    assert result["stations"] == []


def test_native_arcgis_point_response_supports_public_facility_markers():
    client = FakeStationClient({
        "geometryType": "esriGeometryPoint",
        "spatialReference": {"wkid": 4326},
        "features": [
            {"attributes": {"NAME": "Public EMS Station 2", "CITY":"CLEVELAND","STATE":"OH",
                            "ADDRESS": "PUBLIC STATION ADDRESS"},
             "geometry": {"x": -81.67, "y": 41.48}},
            {"attributes": {"NAME": "Bad geometry","CITY":"CLEVELAND","STATE":"OH"},
             "geometry": {"x": 2000000, "y": 500000}},
        ]
    })
    result = get_ems_stations(client=client)
    assert result["status"] == "ready"
    assert len(result["stations"]) == 1
    assert result["stations"][0]["name"] == "Public EMS Station 2"
    assert result["stations"][0]["lat"] == 41.48
    assert result["stations"][0]["lon"] == -81.67
