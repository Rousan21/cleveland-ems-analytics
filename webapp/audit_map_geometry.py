"""Diagnose official Cleveland neighborhood geometry and prevent distorted maps.

Geographic longitude/latitude MUST match WGS84 (GeoJSON). An unexpected
polygon far outside the city can cause Leaflet.fitBounds to zoom all the way
out; accidental latitude/longitude swaps or invalid coordinates do the same.
"""
from math import isfinite
from geography import get_boundaries

CLEVELAND_BOUNDS = (-82.0, 41.30, -81.4, 41.70)


def _pairs(coordinates):
    if not isinstance(coordinates, list):
        raise ValueError("Malformed GeoJSON coordinates")
    if (len(coordinates) >= 2 and all(
        isinstance(v, (int, float)) and not isinstance(v, bool) for v in coordinates[:2]
    )):
        yield coordinates[0], coordinates[1]
    else:
        for inner in coordinates:
            yield from _pairs(inner)


def inspect_boundaries(collection):
    features=collection.get("features") or []
    if not 25 <= len(features) <= 50:
        raise ValueError(f"Unexpected Cleveland polygon count: {len(features)}")
    lonmin,latmin,lonmax,latmax=CLEVELAND_BOUNDS
    names=set()
    points=0
    lowx=lowy=float("inf")
    highx=highy=float("-inf")
    for i,feature in enumerate(features):
        name=str(feature.get("properties",{}).get("name") or "").strip()
        if not name or name in names:
            raise ValueError(f"Missing or duplicated neighborhood: {i}")
        names.add(name)
        geom=feature.get("geometry") or {}
        if geom.get("type") not in ("Polygon","MultiPolygon"):
            raise ValueError(f"Unsupported geometry for {name}")
        coords=list(_pairs(geom.get("coordinates")))
        if len(coords)<4:
            raise ValueError(f"Too few shape points: {name}")
        for lon,lat in coords:
            if not isfinite(lon) or not isfinite(lat):
                raise ValueError(f"Non-finite coordinate: {name}")
            if not(lonmin<=lon<=lonmax and latmin<=lat<=latmax):
                raise ValueError(
                    f"Invalid Cleveland geography: {name} contains "
                    f"lon={lon}, lat={lat}; expected WGS84 lon/lat near Cleveland"
                )
            lowx=min(lowx,lon);highx=max(highx,lon)
            lowy=min(lowy,lat);highy=max(highy,lat)
            points+=1
    result={
        "features":len(features),
        "vertices":points,
        "longitude_bounds":(round(lowx,5),round(highx,5)),
        "latitude_bounds":(round(lowy,5),round(highy,5)),
        "longitude_span":round(highx-lowx,5),
        "latitude_span":round(highy-lowy,5),
        "sample_neighborhoods":sorted(names)[:8],
    }
    if result["longitude_span"]>.50 or result["latitude_span"]>.35:
        raise ValueError(f"Map extends too far for City of Cleveland: {result}")
    return result


if __name__=="__main__":
    print("Official Cleveland GeoJSON geometry QA:",inspect_boundaries(get_boundaries()),flush=True)
