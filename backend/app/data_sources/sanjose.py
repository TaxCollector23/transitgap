"""San Jose municipal sidewalk data source configuration and bounded fetch."""
from __future__ import annotations

import os
import math
from pathlib import Path
from typing import Any

from ..data_loader import CENTER, DEFAULT_RADIUS_M, data_dir
from .arcgis import ArcGISUnavailable, fetch_feature_layer, load_cached_or_stale

LAYER_URL = "https://geo.sanjoseca.gov/server/rest/services/OPN/OPN_OpenDataService/MapServer/185"
ITEM_INFO_URL = "https://geo.sanjoseca.gov/server/rest/services/OPN/OPN_OpenDataService/MapServer/info/iteminfo"
SOURCE_NAME = "City of San Jose Sidewalks"


def study_area_bbox(center: tuple[float, float] = CENTER, radius_m: int = DEFAULT_RADIUS_M) -> tuple[float, float, float, float]:
    """Return a conservative WGS84 envelope around the configured circular area."""
    lat, lon = center
    lat_delta = radius_m / 110_900
    lon_delta = radius_m / (110_900 * max(0.1, math.cos(math.radians(lat))))
    return lon - lon_delta, lat - lat_delta, lon + lon_delta, lat + lat_delta


def load_sidewalks(radius_m: int = DEFAULT_RADIUS_M, directory: Path | None = None,
                   force_refresh: bool | None = None, allow_network: bool = True) -> dict[str, Any]:
    directory = directory or data_dir()
    path = directory / f"sanjose-sidewalks-{radius_m}m.geojson"
    refresh = force_refresh if force_refresh is not None else os.getenv("TRANSITGAP_REFRESH_DATA", "").lower() in {"1", "true", "yes"}
    if not allow_network and not refresh:
        cached = load_cached_or_stale(path, ArcGISUnavailable("Network access is disabled during application startup."))
        if cached:
            cached["metadata"].update({"source_name": SOURCE_NAME, "radius_m": radius_m})
            return cached
        return {"type": "FeatureCollection", "metadata": {
            "source_name": SOURCE_NAME, "source_organization": "City of San Jose",
            "source_url": LAYER_URL, "availability": "unavailable",
            "error": "No packaged San Jose sidewalk snapshot is available.",
        }, "features": []}
    try:
        result = fetch_feature_layer(layer_url=LAYER_URL, item_info_url=ITEM_INFO_URL,
                                     bbox=study_area_bbox(radius_m=radius_m), cache_path=path,
                                     force_refresh=refresh)
    except (ArcGISUnavailable, OSError, ValueError) as exc:
        result = load_cached_or_stale(path, exc)
        if result is None:
            return {"type": "FeatureCollection", "metadata": {
                "source_name": SOURCE_NAME, "source_organization": "City of San Jose",
                "source_url": LAYER_URL, "availability": "unavailable",
                "error": "San Jose sidewalk GIS is unavailable and no cached snapshot exists.",
            }, "features": []}
    result["metadata"].update({"source_name": SOURCE_NAME, "radius_m": radius_m})
    return result
