"""Evidence-aware comparison of municipal sidewalk polygons and OSM paths."""
from __future__ import annotations

import hashlib
import logging
import os
import random
from collections import defaultdict
from typing import Any

import networkx as nx
from pyproj import Transformer
from shapely import make_valid
from shapely.geometry import LineString, Point, shape, mapping
from shapely.ops import linemerge, transform, unary_union
from shapely.strtree import STRtree

from .accessibility import _public_access, _values
from .data_loader import CENTER, DEFAULT_RADIUS_M
from .geospatial import distance_m
from .routing import _geometry_coords

logger = logging.getLogger(__name__)
MATCH_DISTANCE_M = 5.0
REVIEW_DISTANCE_M = 14.0
ROUTE_IMPACT_DISTANCE_M = 18.0
ROUTE_SAMPLE_SEED = 7331
ROUTE_SAMPLE_COUNT = 30
PRIORITY_WEIGHTS = {"route_impact": 0.40, "stop_impact": 0.25, "missing_information": 0.25, "source_conflict": 0.10}
TO_METERS = Transformer.from_crs("EPSG:4326", "EPSG:26910", always_xy=True)
FROM_METERS = Transformer.from_crs("EPSG:26910", "EPSG:4326", always_xy=True)


def _project(geometry):
    return transform(TO_METERS.transform, geometry)


def _unproject(geometry):
    return transform(FROM_METERS.transform, geometry)


def _polygonal(geometry):
    if geometry.geom_type in {"Polygon", "MultiPolygon"}:
        return geometry
    parts = [part for part in getattr(geometry, "geoms", []) if part.geom_type == "Polygon"]
    return unary_union(parts) if parts else None


def _feature_id(feature: dict[str, Any], prefix: str) -> str:
    properties = feature.get("properties") or {}
    value = feature.get("id", properties.get("OBJECTID"))
    if value is None:
        canonical = str(feature.get("geometry", {})).encode("utf-8")
        value = hashlib.sha256(canonical).hexdigest()[:16]
    return f"{prefix}:{value}"


def _metric_circle(center: tuple[float, float], radius_m: int):
    return _project(Point(center[1], center[0])).buffer(radius_m)


def _city_records(dataset: dict[str, Any], center: tuple[float, float], radius_m: int):
    circle = _metric_circle(center, radius_m)
    records = []
    rejected = 0
    for raw in dataset.get("features", []):
        try:
            geometry = shape(raw["geometry"])
            if not geometry.is_valid:
                geometry = make_valid(geometry)
            geometry = _polygonal(geometry)
            if geometry is None or geometry.is_empty:
                rejected += 1
                continue
            projected = _project(geometry).intersection(circle)
            projected = _polygonal(projected)
            if projected is None or projected.is_empty or projected.area <= 0:
                continue
            properties = dict(raw.get("properties") or {})
            source_id = _feature_id(raw, "city-sidewalk")
            records.append({
                "id": source_id,
                "source_feature_id": str(raw.get("id", properties.get("OBJECTID", "unknown"))),
                "properties": properties,
                "geometry_m": projected,
                "geometry": mapping(_unproject(projected)),
                "centroid_m": projected.representative_point(),
            })
        except Exception as exc:
            rejected += 1
            logger.debug("Skipping invalid municipal sidewalk feature: %s", exc)
    return records, rejected


def _osm_records(graph: nx.MultiDiGraph, center: tuple[float, float], radius_m: int):
    circle = _metric_circle(center, radius_m)
    west, south, east, north = _unproject(circle).bounds
    grouped: dict[str, dict[str, Any]] = {}
    explicit_path_classes = {"footway", "path", "pedestrian", "steps", "bridleway"}
    for u, v, key, attrs in graph.edges(keys=True, data=True):
        highway = {value.lower() for value in _values(attrs.get("highway"))}
        explicit_footway = bool(highway & explicit_path_classes) or bool(_values(attrs.get("footway")))
        if not explicit_footway or not _public_access(attrs):
            continue
        try:
            coordinates = _geometry_coords(attrs.get("geometry"))
            if len(coordinates) < 2:
                start, end = graph.nodes[u], graph.nodes[v]
                coordinates = [[float(start["x"]), float(start["y"])], [float(end["x"]), float(end["y"])]]
            if (max(point[0] for point in coordinates) < west or min(point[0] for point in coordinates) > east
                    or max(point[1] for point in coordinates) < south or min(point[1] for point in coordinates) > north):
                continue
            line = _project(LineString(coordinates)).intersection(circle)
            if line.is_empty or line.length <= 0:
                continue
            way_ids = _values(attrs.get("osmid"))
            feature_id = f"osm-way:{way_ids[0]}" if way_ids else f"osm-edge:{u}:{v}:{key}"
            if feature_id not in grouped:
                grouped[feature_id] = {"id": feature_id, "properties": dict(attrs), "parts": []}
            grouped[feature_id]["parts"].append(line)
        except (KeyError, TypeError, ValueError):
            continue
    records = []
    for feature_id, data in grouped.items():
        try:
            merged = unary_union(data["parts"])
            geometry = linemerge(merged) if merged.geom_type in {"MultiLineString", "GeometryCollection"} else merged
            if geometry.is_empty:
                continue
            representative = geometry.interpolate(0.5, normalized=True) if geometry.geom_type == "LineString" else geometry.representative_point()
            records.append({"id": feature_id, "properties": data["properties"], "geometry_m": geometry,
                            "geometry": mapping(_unproject(geometry)), "centroid_m": representative})
        except (TypeError, ValueError):
            continue
    return records


def _attribute_state(city: dict[str, Any] | None, osm: dict[str, Any] | None) -> tuple[list[str], dict[str, Any]]:
    missing: list[str] = []
    observed: dict[str, Any] = {}
    city_props = (city or {}).get("properties", {})
    osm_props = (osm or {}).get("properties", {})
    fields = []
    if city:
        fields.extend((("municipal ADA compliance record", "ADACOMPLY", "city"),
                       ("municipal sidewalk width", "WIDTH", "city")))
    if osm:
        fields.extend((("OSM surface", "surface", "osm"), ("OSM smoothness", "smoothness", "osm"),
                       ("OSM wheelchair tag", "wheelchair", "osm"), ("OSM incline", "incline", "osm"),
                       ("OSM tactile paving", "tactile_paving", "osm"), ("OSM kerb", "kerb", "osm")))
    for label, key, source in fields:
        value = city_props.get(key) if source == "city" else osm_props.get(key)
        if value is None or str(value).strip() == "":
            missing.append(label)
        else:
            observed[label] = value
    return missing, observed


def _comparison_status(city: dict[str, Any], nearest_osm: list[tuple[float, dict[str, Any]]]) -> str:
    matching = [(distance, feature) for distance, feature in nearest_osm if distance <= MATCH_DISTANCE_M]
    close = [(distance, feature) for distance, feature in nearest_osm if distance <= REVIEW_DISTANCE_M]
    distinct_matches = {feature["id"] for _, feature in matching}
    if len(distinct_matches) > 1:
        return "NEEDS_REVIEW"
    if len(distinct_matches) == 1:
        return "DOCUMENTED_IN_MULTIPLE_SOURCES"
    if close:
        return "NEEDS_REVIEW"
    return "DOCUMENTED_IN_CITY_ONLY"


def _sample_routes(graph: nx.MultiDiGraph, stops: list[dict[str, Any]], center: tuple[float, float], radius_m: int):
    if not graph.number_of_nodes() or not stops:
        return []
    rng = random.Random(ROUTE_SAMPLE_SEED)
    # Evaluate graph nodes as reproducible sample origins; they are not residents,
    # measured trips, ridership, or a representative travel-demand sample.
    candidates = []
    for node, attrs in graph.nodes(data=True):
        try:
            point = (float(attrs["y"]), float(attrs["x"]))
            if distance_m(center, point) <= radius_m:
                candidates.append((str(node), node, point))
        except (KeyError, TypeError, ValueError):
            continue
    candidates.sort(key=lambda item: item[0])
    if not candidates:
        return []
    stop_candidates = []
    for stop in stops:
        node = stop.get("graph_node")
        if node not in graph and isinstance(node, str) and node.isdigit():
            node = int(node)
        if node in graph and distance_m(center, (float(stop["latitude"]), float(stop["longitude"]))) <= radius_m:
            stop_candidates.append({**stop, "graph_node": node})
    if not stop_candidates:
        return []
    origin_order = list(candidates)
    rng.shuffle(origin_order)
    stop_order = list(stop_candidates)
    rng.shuffle(stop_order)
    routes = []
    seen = set()
    from .models import Algorithm, Profile
    from .routing import calculate_route
    attempts = 0
    while len(routes) < ROUTE_SAMPLE_COUNT and attempts < len(origin_order) * 2:
        origin_id, origin_node, origin = origin_order[attempts % len(origin_order)]
        stop = stop_order[(attempts * 7) % len(stop_order)]
        attempts += 1
        route_key = (origin_id, str(stop["stop_id"]))
        if route_key in seen or origin_node == stop.get("graph_node"):
            continue
        seen.add(route_key)
        try:
            route = calculate_route(graph, origin, stop["graph_node"], Algorithm.astar, Profile.standard, stop)
            geometry = shape(route["geometry"])
            projected = _project(geometry)
            routes.append({"route_id": f"sample:{origin_id}:{stop['stop_id']}",
                           "stop_id": str(stop["stop_id"]), "geometry_m": projected})
        except (LookupError, ValueError, nx.NetworkXException, KeyError, TypeError):
            continue
    return routes


class GroundTruthIndex:
    """An immutable in-memory index for map queries and inspection priorities."""

    def __init__(self, graph: nx.MultiDiGraph, stops: list[dict[str, Any]],
                 city_dataset: dict[str, Any], radius_m: int = DEFAULT_RADIUS_M,
                 center: tuple[float, float] = CENTER):
        self.radius_m = radius_m
        self.center = center
        self.analysis_area_m = _metric_circle(center, radius_m)
        self.city_metadata = dict(city_dataset.get("metadata") or {})
        self.city_available = self.city_metadata.get("availability") in {"live", "cached", "stale"}
        self.city_records, self.invalid_city_features = _city_records(city_dataset, center, radius_m) if self.city_available else ([], 0)
        self.osm_records = _osm_records(graph, center, radius_m)
        self.city_tree = STRtree([item["geometry_m"] for item in self.city_records]) if self.city_records else None
        self.osm_tree = STRtree([item["geometry_m"] for item in self.osm_records]) if self.osm_records else None
        self.stop_points = [(stop, _project(Point(stop["longitude"], stop["latitude"]))) for stop in stops
                            if distance_m(center, (float(stop["latitude"]), float(stop["longitude"]))) <= radius_m + 150]
        self.sample_routes = _sample_routes(graph, stops, center, radius_m)
        self.gaps: list[dict[str, Any]] = []
        self.by_id: dict[str, dict[str, Any]] = {}
        self._compare()
        self._prioritize()
        self.generated_at = self.city_metadata.get("retrieved_at")

    def _query(self, tree, records, geometry, search_distance: float = 0):
        if tree is None:
            return []
        results = []
        query_geometry = geometry.buffer(search_distance) if search_distance else geometry
        for index in tree.query(query_geometry):
            item = records[int(index)]
            results.append((geometry.distance(item["geometry_m"]), item))
        return sorted(results, key=lambda pair: (pair[0], pair[1]["id"]))

    def _nearby_stops(self, point) -> list[dict[str, Any]]:
        near = sorted(((point.distance(projected), stop) for stop, projected in self.stop_points),
                      key=lambda pair: (pair[0], str(pair[1]["stop_id"])))
        return [dict(stop_id=str(stop["stop_id"]), stop_name=stop["stop_name"], distance_m=round(distance, 1))
                for distance, stop in near if distance <= 150][:3]

    def _add_candidate(self, record: dict[str, Any], classification: str,
                       city: dict[str, Any] | None, osm: dict[str, Any] | None,
                       explanation: str, matched_distance: float | None = None):
        missing, observed = _attribute_state(city, osm)
        point = record["centroid_m"]
        lon, lat = _unproject(point).coords[0]
        source_ids = [source["id"] for source in (city, osm) if source]
        category = "unknown_attribute" if missing else classification.lower()
        stable_key = "|".join([classification, *source_ids, *missing])
        candidate_id = "gap:" + hashlib.sha256(stable_key.encode()).hexdigest()[:20]
        if candidate_id in self.by_id:
            return
        candidate = {
            "id": candidate_id,
            "latitude": float(lat), "longitude": float(lon),
            "category": category,
            "classification": classification,
            "source_feature_ids": source_ids,
            "explanation": explanation,
            "nearby_stops": self._nearby_stops(point),
            "observations_available": observed,
            "missing_information": missing,
            "matched_distance_m": round(matched_distance, 2) if matched_distance is not None else None,
            "provenance": {
                "municipal_source": {
                    "name": self.city_metadata.get("source_name", "City of San Jose Sidewalks"),
                    "url": self.city_metadata.get("source_url"),
                    "feature_id": city.get("source_feature_id") if city else None,
                    "status": "SOURCE_DOCUMENTED" if city else None,
                    "last_update": (city or {}).get("properties", {}).get("LASTUPDATE"),
                    "imported_at": self.city_metadata.get("retrieved_at"),
                } if city else None,
                "osm_source": {
                    "name": "OpenStreetMap pedestrian ways",
                    "url": "https://www.openstreetmap.org/",
                    "feature_id": osm.get("id") if osm else None,
                    "status": "SOURCE_DOCUMENTED" if osm else None,
                } if osm else None,
                "interpretation": "Source documentation is not an independent field inspection. Proximity is not proof of physical connection or accessibility.",
            },
            "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
            "point_m": point,
            "city_record": city,
            "osm_record": osm,
        }
        self.gaps.append(candidate)
        self.by_id[candidate_id] = candidate

    def _compare(self):
        if self.city_available:
            for city in self.city_records:
                # Use the spatial index for local candidates, then calculate exact
                # polygon-to-line distances in EPSG:26910.
                exact = self._query(self.osm_tree, self.osm_records,
                                    city["geometry_m"], REVIEW_DISTANCE_M)
                matching = [(d, item) for d, item in exact if d <= MATCH_DISTANCE_M]
                classification = _comparison_status(city, exact)
                osm = matching[0][1] if matching else (exact[0][1] if classification == "NEEDS_REVIEW" and exact else None)
                if classification == "DOCUMENTED_IN_MULTIPLE_SOURCES":
                    explanation = "City sidewalk polygon and an explicit OSM pedestrian path are spatially close. This is a proximity match, not proof they are the same facility or are accessible."
                elif classification == "NEEDS_REVIEW":
                    explanation = "The sources are close or ambiguous, so TransitGap cannot determine whether they describe the same pedestrian facility."
                else:
                    explanation = "The City dataset contains a sidewalk polygon with no sufficiently close explicit OSM pedestrian path. This is a source coverage difference, not proof that a sidewalk or path is missing."
                self._add_candidate(city, classification, city, osm, explanation,
                                    matching[0][0] if matching else (exact[0][0] if exact else None))
                if classification == "DOCUMENTED_IN_MULTIPLE_SOURCES" and osm:
                    city_width = city["properties"].get("WIDTH")
                    osm_width = osm["properties"].get("width")
                    if city_width not in (None, "") and osm_width not in (None, "") and str(city_width).strip() != str(osm_width).strip():
                        self._add_candidate(city, "CONFLICTING_SOURCES", city, osm,
                                            "The municipal and OSM width fields contain different source values. Units and measurement methods may differ, so review is required.", matching[0][0])

        if not self.city_available:
            # Never classify an OSM feature as OSM-only when the comparison source is unavailable.
            for osm in self.osm_records:
                if any(not _values(osm["properties"].get(tag)) for tag in ("surface", "smoothness", "wheelchair", "width")):
                    self._add_candidate(osm, "UNKNOWN_ATTRIBUTE", None, osm,
                                        "Some accessibility attributes are not documented on this OSM path. The municipal comparison source is unavailable.")
            return

        for osm in self.osm_records:
            near_city = self._query(self.city_tree, self.city_records,
                                    osm["geometry_m"], REVIEW_DISTANCE_M)
            close = [(d, city) for d, city in near_city if d <= MATCH_DISTANCE_M]
            if close:
                continue
            ambiguous = [(d, city) for d, city in near_city if d <= REVIEW_DISTANCE_M]
            if ambiguous:
                continue
            self._add_candidate(osm, "DOCUMENTED_IN_OSM_ONLY", None, osm,
                                "An explicit OSM pedestrian path has no corresponding municipal polygon within the configured match tolerance. This does not prove the city data is complete or that infrastructure is absent.")

    def _prioritize(self):
        routes = self.sample_routes
        for candidate in self.gaps:
            point = candidate["point_m"]
            affected = [route for route in routes if point.distance(route["geometry_m"]) <= ROUTE_IMPACT_DISTANCE_M]
            route_count = len({route["route_id"] for route in affected})
            stop_count = len({route["stop_id"] for route in affected})
            candidate["evaluated_route_count"] = route_count
            candidate["affected_vta_stop_count"] = stop_count
            candidate["evaluated_routes_total"] = len(routes)
            candidate["priority_score"] = None
            candidate["score_components"] = None

        if not routes:
            return
        max_routes = max((candidate["evaluated_route_count"] for candidate in self.gaps), default=0) or 1
        max_stops = max((candidate["affected_vta_stop_count"] for candidate in self.gaps), default=0) or 1
        for candidate in self.gaps:
            missing_count = len(candidate["missing_information"])
            route_norm = candidate["evaluated_route_count"] / max_routes
            stop_norm = candidate["affected_vta_stop_count"] / max_stops
            missing_norm = min(1.0, missing_count / 5.0)
            conflict = candidate["classification"] == "CONFLICTING_SOURCES"
            components = {
                "weights": dict(PRIORITY_WEIGHTS),
                "route_impact": {"raw_count": candidate["evaluated_route_count"], "denominator": len(routes), "normalized": route_norm},
                "stop_impact": {"raw_count": candidate["affected_vta_stop_count"], "denominator": len({route["stop_id"] for route in routes}), "normalized": stop_norm},
                "missing_information": {"raw_count": missing_count, "denominator": 5, "normalized": missing_norm},
                "source_conflict": {"raw_count": int(conflict), "normalized": int(conflict)},
                "route_sample_seed": ROUTE_SAMPLE_SEED,
                "route_impact_distance_m": ROUTE_IMPACT_DISTANCE_M,
            }
            score = 100 * (PRIORITY_WEIGHTS["route_impact"] * route_norm
                           + PRIORITY_WEIGHTS["stop_impact"] * stop_norm
                           + PRIORITY_WEIGHTS["missing_information"] * missing_norm
                           + PRIORITY_WEIGHTS["source_conflict"] * int(conflict))
            candidate["priority_score"] = round(score, 2)
            candidate["score_components"] = components
            candidate["explanation"] = (
                f"This candidate is within {ROUTE_IMPACT_DISTANCE_M:g} m of {candidate['evaluated_route_count']} of "
                f"{len(routes)} reproducibly sampled graph-origin routes to {candidate['affected_vta_stop_count']} "
                f"distinct VTA stops, with {missing_count} relevant information fields unknown. "
                "These samples are not pedestrian traffic or ridership."
            )
        self.gaps.sort(key=lambda item: (-(item["priority_score"] or 0), item["id"]))

    def source_status(self) -> dict[str, Any]:
        return {
            "sources": [
                {"id": "osm-pedestrian-network", "name": "OpenStreetMap pedestrian network",
                 "status": "ready", "url": "https://www.openstreetmap.org/",
                 "feature_count": len(self.osm_records), "attribution": "© OpenStreetMap contributors",
                 "evidence_status": "SOURCE_DOCUMENTED", "limitations": "OpenStreetMap tags may be absent or outdated; mapped data is not a field inspection."},
                {"id": "city-sidewalks", "name": self.city_metadata.get("source_name", "City of San Jose Sidewalks"),
                 "status": self.city_metadata.get("availability", "unavailable"),
                 "url": self.city_metadata.get("source_url"), "retrieved_at": self.city_metadata.get("retrieved_at"),
                 "feature_count": len(self.city_records), "attribution": self.city_metadata.get("service_attribution", "City of San Jose"),
                 "license_info": self.city_metadata.get("license_info"), "license_note": self.city_metadata.get("license_note"),
                 "coverage_radius_m": self.radius_m,
                 "coverage_center": {"latitude": self.center[0], "longitude": self.center[1]},
                 "limitations": "The City disclaims accuracy warranties. Polygon proximity does not prove accessibility or topological connection."},
                {"id": "vta-gtfs", "name": "VTA GTFS static stops", "status": "ready",
                 "url": "https://gtfs.vta.org/", "feature_count": len(self.stop_points),
                 "evidence_status": "SOURCE_DOCUMENTED", "limitations": "Static transit stop feed; it does not describe sidewalk access."},
            ],
            "study_area": {"center": {"latitude": self.center[0], "longitude": self.center[1]}, "radius_m": self.radius_m,
                           "analysis_crs": "EPSG:26910"},
            "matching": {"distance_m": MATCH_DISTANCE_M, "review_distance_m": REVIEW_DISTANCE_M,
                         "note": "Distance is measured in EPSG:26910. A match is proximity only; roads and separate sidewalk sides are not assumed equivalent."},
            "generated_at": self.generated_at,
        }

    def _public_candidate(self, candidate: dict[str, Any], include_geometry: bool = True) -> dict[str, Any]:
        result = {key: value for key, value in candidate.items()
                  if key not in {"point_m", "city_record", "osm_record"}}
        if not include_geometry:
            result.pop("geometry", None)
        return result

    def get_gaps(self, *, west: float | None = None, south: float | None = None,
                 east: float | None = None, north: float | None = None,
                 limit: int = 100, offset: int = 0) -> dict[str, Any]:
        selected = self.gaps
        if None not in (west, south, east, north):
            selected = [item for item in selected if west <= item["longitude"] <= east and south <= item["latitude"] <= north]
        page = selected[offset:offset + limit]
        return {"count": len(selected), "limit": limit, "offset": offset,
                "features": [self._public_candidate(item) for item in page],
                "generated_at": self.generated_at}

    def get_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        candidate = self.by_id.get(candidate_id)
        return self._public_candidate(candidate) if candidate else None

    def get_priorities(self, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        candidates = self.gaps[offset:offset + limit]
        return {"count": len(self.gaps), "limit": limit, "offset": offset,
                "evaluated_routes": len(self.sample_routes), "route_sample_seed": ROUTE_SAMPLE_SEED,
                "weights": dict(PRIORITY_WEIGHTS),
                "note": "Inspection suggestions only, not an official government priority and not a measure of pedestrian traffic or ridership.",
                "candidates": [self._public_candidate(item, include_geometry=False) for item in candidates],
                "generated_at": self.generated_at}

    def municipal_features(self, west: float | None, south: float | None, east: float | None,
                           north: float | None, limit: int = 300, offset: int = 0):
        bbox = None
        if None not in (west, south, east, north):
            bbox = (west, south, east, north)
        features = []
        projected_view = None
        if bbox:
            projected_view = _project(shape({"type": "Polygon", "coordinates": [[
                [west, south], [east, south], [east, north], [west, north], [west, south]
            ]]}))
        for record in self.city_records:
            if projected_view is not None and not record["geometry_m"].intersects(projected_view):
                continue
            properties = dict(record["properties"])
            properties.update({"source_feature_id": record["source_feature_id"], "evidence_status": "SOURCE_DOCUMENTED",
                               "source_name": "City of San Jose Sidewalks",
                               "source_url": self.city_metadata.get("source_url"),
                               "retrieved_at": self.city_metadata.get("retrieved_at"),
                               "interpretation": "City sidewalk polygon record; not proof of a field-verified or accessible pedestrian route."})
            features.append({"type": "Feature", "id": record["id"], "geometry": record["geometry"], "properties": properties})
        page = features[offset:offset + limit]
        return {"type": "FeatureCollection", "features": page,
                "count": len(features), "limit": limit, "offset": offset,
                "source": self.city_metadata}

    def route_evidence(self, route_geometry: dict[str, Any], limit: int = 20):
        if not self.city_available:
            return {"status": "unavailable", "nearby_feature_count": 0, "features": [],
                    "message": "Municipal sidewalk data is unavailable; no comparison is inferred."}
        try:
            route = _project(shape(route_geometry))
        except (TypeError, ValueError, KeyError):
            return {"status": "unavailable", "nearby_feature_count": 0, "features": [], "message": "Route geometry could not be compared."}
        if not route.buffer(15).intersects(self.analysis_area_m):
            return {"status": "outside_municipal_snapshot", "nearby_feature_count": 0, "features": [],
                    "message": "No City of San Jose sidewalk comparison is available along this route. The current municipal evidence snapshot is limited to the Diridon pilot area."}
        nearby = self._query(self.city_tree, self.city_records, route, 15)
        selected = []
        for distance, city in nearby[:limit]:
            props = city["properties"]
            selected.append({"source_feature_id": city["source_feature_id"], "distance_to_route_m": round(distance, 1),
                             "ada_compliance_record": props.get("ADACOMPLY"), "width_record": props.get("WIDTH"),
                             "last_update": props.get("LASTUPDATE"), "status": "SOURCE_DOCUMENTED",
                             "source_name": "City of San Jose Sidewalks", "source_url": self.city_metadata.get("source_url"),
                             "relationship": "Polygon is spatially near the route; it is not confirmed to be the traveled path or accessible."})
        return {"status": "ready", "nearby_feature_count": len(nearby), "features": selected,
                "distance_threshold_m": 15,
                "message": "City sidewalk polygons near this route are spatial context, not evidence that the route uses those sidewalks."}

    def find_candidate_for_point(self, latitude: float, longitude: float, max_distance_m: float = 25):
        point = _project(Point(longitude, latitude))
        nearby = sorted(((point.distance(item["point_m"]), item) for item in self.gaps),
                        key=lambda pair: (pair[0], pair[1]["id"]))
        if not nearby or nearby[0][0] > max_distance_m:
            return None
        if len(nearby) > 1 and abs(nearby[1][0] - nearby[0][0]) < 1.0:
            return None
        return nearby[0][1]["id"]

    def evaluation(self) -> dict[str, Any]:
        counts: dict[str, int] = defaultdict(int)
        for gap in self.gaps:
            counts[gap["classification"]] += 1
        return {"study_area_radius_m": self.radius_m, "analysis_crs": "EPSG:26910",
                "municipal_features_after_study_area_clip": len(self.city_records),
                "invalid_municipal_features_skipped": self.invalid_city_features,
                "explicit_osm_pedestrian_features": len(self.osm_records),
                "candidate_count": len(self.gaps), "classification_counts": dict(counts),
                "evaluated_route_pairs": len(self.sample_routes),
                "distinct_vta_stops_in_routes": len({route["stop_id"] for route in self.sample_routes}),
                "route_sample_seed": ROUTE_SAMPLE_SEED,
                "route_impact_distance_m": ROUTE_IMPACT_DISTANCE_M,
                "matching_tolerance_m": MATCH_DISTANCE_M,
                "review_tolerance_m": REVIEW_DISTANCE_M,
                "limitations": ["No field validation was performed.", "Route samples are deterministic graph-origin to GTFS-stop paths, not pedestrian demand or ridership.", "City polygons and OSM paths are compared by proximity only; false and ambiguous matches remain possible."]}
