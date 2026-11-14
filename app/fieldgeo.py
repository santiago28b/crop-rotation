"""
Geometry helpers: GeoJSON field polygon -> centroid, area, sample points, projections.

The UI sends a GeoJSON Polygon (WGS84 lon/lat). Everything downstream needs either the
centroid (climate, soil) or a grid of points inside the field (CDL crop history).
"""

from __future__ import annotations

import math

from pyproj import Geod, Transformer
from shapely.geometry import MultiPolygon, Point, Polygon, shape

_GEOD = Geod(ellps="WGS84")
_TO_ALBERS = Transformer.from_crs(4326, 5070, always_xy=True)  # CONUS Albers, what CropScape wants

# Bigger than any single field (about 25,000 acres). A larger outline is almost always
# someone tapping corners while the map is zoomed out to a whole region.
MAX_FIELD_HA = 10_000

# Rough CONUS bounding box: enough to decide "do US-only datasets (CDL, SSURGO) apply here?"
CONUS_BBOX = (-125.0, 24.5, -66.9, 49.5)  # lon_min, lat_min, lon_max, lat_max


def field_polygon(geometry: dict) -> Polygon:
    # Leaflet's layer.toGeoJSON() gives a Feature (or FeatureCollection); unwrap to the geometry
    if geometry.get("type") == "FeatureCollection":
        feats = geometry.get("features") or []
        if not feats:
            raise ValueError("FeatureCollection has no features")
        geometry = feats[0]
    if geometry.get("type") == "Feature":
        geometry = geometry.get("geometry") or {}
    if not geometry.get("coordinates"):
        raise ValueError("geometry has no coordinates")
    geom = shape(geometry)
    if isinstance(geom, Point):
        geom = geom.buffer(0.0004)  # ~45 m radius -> a "field" around a single tap
    if isinstance(geom, MultiPolygon):
        geom = max(geom.geoms, key=lambda g: g.area)  # largest part
    if not isinstance(geom, Polygon):
        raise ValueError(f"Unsupported geometry type {geometry.get('type')}")
    hectares = area_ha(geom)
    if hectares > MAX_FIELD_HA:
        raise ValueError(f"That outline covers about {hectares * 2.47105:,.0f} acres, which is too large "
                         "for one field. Zoom in on the map and outline a single field.")
    return geom


def centroid(poly: Polygon) -> tuple[float, float]:
    c = poly.centroid
    return c.y, c.x  # (lat, lon)


def area_ha(poly: Polygon) -> float:
    area_m2, _ = _GEOD.geometry_area_perimeter(poly)
    return abs(area_m2) / 10_000


def in_conus(lat: float, lon: float) -> bool:
    lon_min, lat_min, lon_max, lat_max = CONUS_BBOX
    return lon_min <= lon <= lon_max and lat_min <= lat <= lat_max


def hemisphere(lat: float) -> str:
    return "N" if lat >= 0 else "S"


def to_albers(lon: float, lat: float) -> tuple[float, float]:
    return _TO_ALBERS.transform(lon, lat)


def sample_points(poly: Polygon, spacing_m: float = 40.0, max_points: int = 25) -> list[tuple[float, float]]:
    """
    Regular grid of (lon, lat) points inside the polygon, ~spacing_m apart, capped at
    max_points (grid is coarsened until it fits). Always includes the centroid so tiny
    fields still get one sample.
    """
    lat_c, lon_c = centroid(poly)
    minx, miny, maxx, maxy = poly.bounds
    # degrees per metre at this latitude
    dlat = spacing_m / 111_320
    dlon = spacing_m / (111_320 * max(math.cos(math.radians(lat_c)), 0.1))

    # Start coarse enough that the first grid has only a few times max_points cells.
    # Without this a region-sized outline meant billions of point-in-polygon checks
    # on the event loop, which froze the whole server.
    cells = ((maxx - minx) / dlon) * ((maxy - miny) / dlat)
    if cells > max_points * 8:
        scale = math.sqrt(cells / (max_points * 8))
        dlat *= scale
        dlon *= scale

    while True:
        pts = []
        y = miny + dlat / 2
        while y < maxy:
            x = minx + dlon / 2
            while x < maxx:
                if poly.contains(Point(x, y)):
                    pts.append((x, y))
                x += dlon
            y += dlat
        if len(pts) <= max_points:
            break
        dlat *= 1.5
        dlon *= 1.5

    if not pts or not any(abs(p[0] - lon_c) < 1e-9 and abs(p[1] - lat_c) < 1e-9 for p in pts):
        pts.append((lon_c, lat_c))
    return pts
