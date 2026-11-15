"""Cleveland boundaries and privacy-preserving area aggregates.

This module never derives neighborhood from an unverified block address. Shape
boundaries are sourced from a public ArcGIS GeoJSON feature layer. They are not
incident geometries. Incident geography is imported separately after validation.
"""
import json
from pathlib import Path
from datetime import datetime, timezone

import requests
from sqlalchemy import select, func

from db import EMSCall, EMSArea, SessionLocal
from analytics import get_bounds

BOUNDARY_URL = (
    "https://services7.arcgis.com/ZodPOMBKsdAsTqF4/ArcGIS/rest/services/"
    "Cleveland_Neighborhoods/FeatureServer/147/query"
)
CACHE_FILE = Path(__file__).resolve().parent / "data" / "cleveland_neighborhoods.geojson"
SUPPRESS_BELOW = 11


def _validate_feature_collection(payload):
    if payload.get("type") != "FeatureCollection":
        raise ValueError("Boundary provider returned something other than GeoJSON")
    cleaned = []
    for item in payload.get("features", []):
        name = str(item.get("properties", {}).get("Neighborhood", "")).strip()
        geometry = item.get("geometry")
        if not name or not isinstance(geometry, dict) or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            continue
        if not isinstance(geometry.get("coordinates"), list):
            continue
        cleaned.append({"type": "Feature", "properties": {"name": name}, "geometry": geometry})
    if not (10 <= len(cleaned) <= 150):
        raise ValueError(f"Unexpected number of neighborhood boundaries: {len(cleaned)}")
    return {"type": "FeatureCollection", "features": cleaned}


def get_boundaries(*, client=None, refresh=False):
    """Serve saved boundaries when available. Fetch once when absent or refreshed.

    Cache is local and can be committed into a deployment with licensing review.
    On network failure, serve a previously validated cache, not invented polygons.
    """
    if CACHE_FILE.is_file() and not refresh:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    try:
        response = (client or requests).get(BOUNDARY_URL, params={
            "where": "1=1", "outFields": "Neighborhood", "returnGeometry": "true",
            "outSR": 4326, "resultRecordCount": 2000, "f": "geojson"
        }, timeout=35)
        response.raise_for_status()
        payload = _validate_feature_collection(response.json())
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp = CACHE_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps(payload), encoding="utf-8")
        temp.replace(CACHE_FILE)
        return payload
    except (requests.RequestException, ValueError, KeyError):
        if CACHE_FILE.is_file():
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        raise


# Public EMS station *facilities*, not call locations. Official Cleveland GIS
# layer: EMS_Stations/FeatureServer/0. No incident coordinates are published.
STATIONS_URL = (
    "https://services7.arcgis.com/RLKshC6KfXm2kCVy/ArcGIS/rest/services/"
    "EMS_Stations/FeatureServer/0/query"
)


def get_ems_stations(*, client=None):
    """Get named public EMS facilities with validated WGS84 coordinates.

    Fail gracefully if ArcGIS is unavailable. Never derive incident locations
    from station positions or suggest an unsupported coverage radius.
    """
    unavailable = {
        "status": "unavailable", "stations": [],
        "source": "City of Cleveland public EMS Stations feature layer",
        "note": "Station positions unavailable; these are not incident locations.",
    }
    try:
        response = (client or requests).get(STATIONS_URL, params={
            "where": "1=1", "outFields": "EMS_STATION,ADDRESS",
            "returnGeometry": "true", "outSR": 4326, "f": "geojson",
            "resultRecordCount": 500,
        }, timeout=30)
        response.raise_for_status()
        payload = response.json()
        if payload.get("type") != "FeatureCollection":
            return unavailable
        stations = []
        seen = set()
        for feature in payload.get("features", []):
            props = feature.get("properties") or {}
            geom = feature.get("geometry") or {}
            coord = geom.get("coordinates")
            if geom.get("type") != "Point" or not isinstance(coord, list) or len(coord) < 2:
                continue
            lon, lat = coord[:2]
            if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in [lon, lat]):
                continue
            # Exclude coordinates clearly outside the Cleveland metro area.
            if not (-82.4 <= lon <= -81.0 and 40.8 <= lat <= 42.1):
                continue
            name = str(props.get("EMS_STATION") or "").strip()
            if not name or len(name) > 90:
                continue
            address = str(props.get("ADDRESS") or "").strip()[:120]
            key = (name.casefold(), round(lon, 6), round(lat, 6))
            if key in seen:
                continue
            seen.add(key)
            stations.append({
                "name": name, "address": address,
                "lat": round(lat, 6), "lon": round(lon, 6),
            })
        stations.sort(key=lambda item: item["name"].casefold())
        if not (1 <= len(stations) <= 100):
            return unavailable
        return {
            "status": "ready", "stations": stations,
            "source": "City of Cleveland public EMS Stations feature layer",
            "note": ("Public station locations are contextual facilities, not call "
                     "sites, service areas, availability, or evidence of response coverage."),
        }
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return unavailable


def get_area_summary(*, window='30d', priority='all', start_date=None, end_date=None, now=None):
    """Aggregate only *verified* area assignments; suppress small values.

    Returns no individual addresses, call IDs, points, or unsuppressed small counts.
    """
    start, end = get_bounds(window, start_date, end_date, now)
    with SessionLocal() as db:
        query = (select(EMSArea.neighborhood, func.count(EMSCall.object_id))
                 .join(EMSCall, EMSCall.object_id == EMSArea.object_id)
                 .where(EMSCall.dispatch_time.is_not(None), EMSCall.dispatch_time < end))
        if start:
            query = query.where(EMSCall.dispatch_time >= start)
        if priority != 'all':
            if priority not in {'1','2','3'}:
                raise ValueError('Invalid priority')
            query = query.where(EMSCall.priority == priority)
        result = db.execute(query.group_by(EMSArea.neighborhood)).all()
    matched = sum(count for _,count in result)
    allowed = {name: count for name,count in result if count >= SUPPRESS_BELOW}
    return {
        'status': 'no_verified_geography' if matched == 0 else ('ready' if allowed else 'suppressed'),
        'reporting_threshold': SUPPRESS_BELOW,
        'mapped_records': matched,
        'areas': [{'name': name, 'count': count} for name,count in sorted(allowed.items(), key=lambda p: -p[1])],
        'note': 'Verified neighborhood assignments only. Areas with fewer than 11 calls are not shown.'
    }
