"""Bounded, provenance-preserving ArcGIS REST feature-layer adapter."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ArcGISUnavailable(RuntimeError):
    pass


def _get_json(url: str, params: dict[str, Any], timeout_seconds: float = 20) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = httpx.get(url, params=params, timeout=timeout_seconds, follow_redirects=True)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ArcGISUnavailable("ArcGIS returned a response that was not a JSON object")
            if "error" in payload:
                error = payload["error"]
                raise ArcGISUnavailable(f"ArcGIS query failed: {error.get('message', 'unknown service error')}")
            return payload
        except (httpx.HTTPError, ValueError, ArcGISUnavailable) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.25 * (2 ** attempt))
    raise ArcGISUnavailable(f"ArcGIS service request failed after three attempts: {last_error}") from last_error


def _cached(cache_path: Path, ttl: timedelta) -> dict[str, Any] | None:
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        fetched = datetime.fromisoformat(cached["metadata"]["retrieved_at"])
        if datetime.now(timezone.utc) - fetched.astimezone(timezone.utc) <= ttl:
            cached["metadata"]["availability"] = "cached"
            return cached
    except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return None


def fetch_feature_layer(
    *, layer_url: str, item_info_url: str, bbox: tuple[float, float, float, float],
    cache_path: Path, ttl_hours: int = 24, force_refresh: bool = False,
) -> dict[str, Any]:
    """Fetch only feature IDs intersecting a WGS84 envelope, then batch them.

    Object-ID batching avoids relying on a single response staying below the
    service's maxRecordCount. The cache keeps original feature IDs, attributes,
    WGS84 geometry, source metadata, and a separate import timestamp.
    """
    if not force_refresh:
        fresh = _cached(cache_path, timedelta(hours=ttl_hours))
        if fresh:
            return fresh
    xmin, ymin, xmax, ymax = bbox
    if not (-180 <= xmin < xmax <= 180 and -90 <= ymin < ymax <= 90):
        raise ValueError("ArcGIS study-area bounds must be a valid WGS84 envelope")

    layer = _get_json(layer_url, {"f": "json"})
    capabilities = {part.strip().lower() for part in str(layer.get("capabilities", "")).split(",")}
    if "query" not in capabilities:
        raise ArcGISUnavailable("The ArcGIS layer does not advertise query capability")
    if layer.get("geometryType") != "esriGeometryPolygon":
        raise ArcGISUnavailable("The San Jose sidewalk layer is no longer a polygon layer")
    object_id_field = layer.get("objectIdField") or next(
        (field.get("name") for field in layer.get("fields", []) if field.get("type") == "esriFieldTypeOID"), None
    )
    if not object_id_field:
        raise ArcGISUnavailable("The ArcGIS layer did not identify a stable object ID field")

    query_url = layer_url.rstrip("/") + "/query"
    geometry = {"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax,
                "spatialReference": {"wkid": 4326}}
    base_params = {
        "where": "1=1", "geometry": json.dumps(geometry, separators=(",", ":")),
        "geometryType": "esriGeometryEnvelope", "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects", "returnGeometry": "true",
        "outSR": 4326,
    }
    ids_response = _get_json(query_url, {**base_params, "returnIdsOnly": "true", "f": "json"})
    object_ids = ids_response.get("objectIds")
    if object_ids is None:
        raise ArcGISUnavailable("ArcGIS did not return object IDs for the bounded sidewalk query")
    object_ids = sorted({int(value) for value in object_ids})
    max_record_count = max(1, int(layer.get("maxRecordCount") or 1000))
    batch_size = max(1, min(max_record_count, 500))
    features_by_id: dict[int, dict[str, Any]] = {}
    for offset in range(0, len(object_ids), batch_size):
        batch = object_ids[offset:offset + batch_size]
        payload = _get_json(query_url, {
            "objectIds": ",".join(str(value) for value in batch), "outFields": "*",
            "returnGeometry": "true", "outSR": 4326, "f": "geojson",
        })
        for feature in payload.get("features", []):
            properties = feature.get("properties") or {}
            raw_id = feature.get("id", properties.get(object_id_field))
            if raw_id is None:
                continue
            feature_id = int(raw_id)
            if feature.get("geometry") and feature["geometry"].get("type") in {"Polygon", "MultiPolygon"}:
                features_by_id[feature_id] = {
                    "type": "Feature", "id": feature_id,
                    "geometry": feature["geometry"], "properties": properties,
                }

    retrieved_at = datetime.now(timezone.utc).isoformat()
    metadata = {
        "source_name": layer.get("name", "Sidewalks"),
        "source_organization": layer.get("copyrightText") or "City of San Jose",
        "source_url": layer_url,
        "item_info_url": item_info_url,
        "retrieved_at": retrieved_at,
        "availability": "live",
        "geometry_type": layer.get("geometryType"),
        "source_spatial_reference": (layer.get("sourceSpatialReference") or {}).get("latestWkid"),
        "output_spatial_reference": 4326,
        "object_id_field": object_id_field,
        "max_record_count": max_record_count,
        "query_feature_id_count": len(object_ids),
        "feature_count": len(features_by_id),
        "supported_query_formats": layer.get("supportedQueryFormats"),
        "supports_pagination": (layer.get("advancedQueryCapabilities") or {}).get("supportsPagination"),
        "attribution": layer.get("copyrightText") or "City of San Jose",
        "license_note": "City service metadata provides no accuracy warranty; use at your own risk. No separate open license was identified in the service item metadata.",
        "disclaimer": "City GIS data is provided as-is and may be incomplete, stale, or inaccurate.",
        "study_area_bbox_wgs84": [xmin, ymin, xmax, ymax],
    }
    item_info = _get_json(item_info_url, {"f": "json"})
    metadata["license_info"] = item_info.get("licenseInfo")
    metadata["service_attribution"] = item_info.get("accessInformation") or metadata["attribution"]
    result = {"type": "FeatureCollection", "metadata": metadata,
              "features": list(features_by_id.values())}
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix(cache_path.suffix + ".part")
        temporary.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
        temporary.replace(cache_path)
    except OSError as exc:
        logger.info("Could not persist City of San Jose sidewalk cache: %s", exc)
    return result


def load_cached_or_stale(cache_path: Path, error: Exception) -> dict[str, Any] | None:
    """Return an existing snapshot after an upstream failure, marked honestly."""
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        cached["metadata"]["availability"] = "stale"
        cached["metadata"]["last_refresh_error"] = str(error)
        return cached
    except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError):
        return None
