"""Field geometry helpers (no extra libraries needed)."""

import math

EARTH_RADIUS_M = 6_371_000
SQ_M_PER_ACRE = 4046.8564


def _outer_ring(geojson: dict) -> list:
    """Accept a GeoJSON Feature, Polygon, or a bare ring of [lon, lat] points."""
    if isinstance(geojson, dict):
        if geojson.get("type") == "Feature":
            geojson = geojson["geometry"]
        if geojson.get("type") != "Polygon":
            raise ValueError("field must be a GeoJSON Polygon")
        ring = geojson["coordinates"][0]
    else:
        ring = geojson
    if len(ring) < 3:
        raise ValueError("field polygon needs at least 3 points")
    return ring


def field_center_and_acres(geojson) -> tuple[float, float, float]:
    """Return (lat, lon, acres) for a field polygon drawn on the map."""
    ring = _outer_ring(geojson)
    lon0 = sum(p[0] for p in ring) / len(ring)
    lat0 = sum(p[1] for p in ring) / len(ring)

    # Flatten to meters around the center (accurate enough for farm fields)
    k = math.cos(math.radians(lat0))
    pts = [
        (math.radians(lon - lon0) * EARTH_RADIUS_M * k, math.radians(lat - lat0) * EARTH_RADIUS_M)
        for lon, lat, *_ in ring
    ]
    # Shoelace formula
    area = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        area += x1 * y2 - x2 * y1
    acres = abs(area) / 2 / SQ_M_PER_ACRE
    return round(lat0, 5), round(lon0, 5), round(acres, 1)
