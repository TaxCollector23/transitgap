"""Bounded source-documented vs possible network reach toward actual VTA stops.

This model asks whether the stored OSM evidence is sufficiently complete for a
small set of explicit mobility predicates. It does not identify safe routes.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
import csv
import io
from typing import Any
from zipfile import ZipFile

import networkx as nx
from shapely.geometry import LineString, mapping
from shapely.ops import substring

from .accessibility import _crossing_applies, _values
from .data_loader import CENTER
from .geospatial import distance_m
from .geospatial import nearest_graph_node
from .models import Profile
from .profiles import SPEED_MPS, assess, incline_percent, width_m
from .routing import _edge_coords, _edge_options, _length_m, _public_access, _weight

PILOT_RADIUS_M = 1500
MAX_STOP_CONNECTOR_M = 35
MAX_SAMPLE_SIZE = 300
MAX_MINUTES = 15
VERSION = "diridon-documented-possible-v1"
WARNING = (
    "Documented means recorded in the source data, not field checked or proven usable. "
    "The possible scenario assumes selected unknown conditions are usable; it is not a safe-route guarantee. "
    "Sampled graph origins are not people, population, or an official accessibility statistic."
)
SOURCE_OSM = "https://www.openstreetmap.org/"
SOURCE_GTFS = "https://gtfs.vta.org/gtfs_vta.zip"


def pilot_gtfs_stops(graph: nx.MultiDiGraph, archive_path) -> list[dict[str, Any]]:
    """Read every actual VTA stop in the pilot and keep distant snaps explicit."""
    result = []
    with ZipFile(archive_path) as archive:
        with archive.open("stops.txt") as source:
            reader = csv.DictReader(io.TextIOWrapper(source, encoding="utf-8-sig", newline=""))
            for row in reader:
                try:
                    lat, lon = float(row["stop_lat"]), float(row["stop_lon"])
                except (KeyError, TypeError, ValueError):
                    continue
                if distance_m(CENTER, (lat, lon)) > PILOT_RADIUS_M:
                    continue
                try:
                    node, connector_distance = nearest_graph_node(graph, lat, lon)
                except (LookupError, ValueError):
                    node, connector_distance = None, math.inf
                result.append({
                    "stop_id": row.get("stop_id", ""),
                    "stop_name": row.get("stop_name", ""),
                    "latitude": lat,
                    "longitude": lon,
                    "graph_node": str(node) if node is not None else None,
                    "connector_distance_m": round(connector_distance, 1) if math.isfinite(connector_distance) else None,
                    "wheelchair_boarding": int(row.get("wheelchair_boarding") or 0),
                })
    return result


def critical_unknowns(edge: dict[str, Any], start: dict[str, Any], end: dict[str, Any], profile: Profile) -> tuple[str, ...]:
    """Return missing predicates relevant to this edge and profile only.

    Surface is relevant on mapped pedestrian paths. Width is checked on
    footway/path/pedestrian ways, not on every street edge. A directional-only
    incline is unknown. Crossing attributes are considered only at mapped
    crossing transitions. Other absent OSM keys are not treated as predicates.
    """
    name = profile.value
    if name == "avoid_mapped_stairs":
        name = "wheelchair"
    if name not in {"standard", "wheelchair", "stroller", "low_vision"}:
        raise ValueError(f"Profile {name!r} is not supported by this study")
    if name == "standard":
        return ()

    unknown: list[str] = []
    highway = {v.lower() for v in _values(edge.get("highway"))}
    pedestrian_way = bool(
        highway & {"footway", "path", "pedestrian", "steps"}
        or _values(edge.get("footway"))
    )
    if name in {"wheelchair", "stroller"} and pedestrian_way:
        if not _values(edge.get("surface")):
            unknown.append("surface")
        if not any(width_m(value) is not None for value in _values(edge.get("width"))):
            unknown.append("width")
        if _values(edge.get("incline")) and not any(
            incline_percent(value) is not None for value in _values(edge.get("incline"))
        ):
            unknown.append("incline_grade")
        surfaces = {v.lower() for v in _values(edge.get("surface"))}
        if surfaces & {"gravel", "unpaved", "dirt", "grass", "sett", "cobblestone", "sand"} and not _values(edge.get("smoothness")):
            unknown.append("smoothness")

    if name == "low_vision" and pedestrian_way and not _values(edge.get("lit")):
        unknown.append("lighting")

    if _crossing_applies(edge, start, end):
        places = (edge, start, end)
        if name in {"wheelchair", "stroller"} and not any(_values(place.get("kerb")) for place in places):
            unknown.append("crossing_kerb")
        if name == "low_vision":
            if not any(_values(place.get("tactile_paving")) for place in places):
                unknown.append("tactile_paving")
            if not any(_values(place.get("crossing:signals")) or _values(place.get("traffic_signals:sound")) for place in places):
                unknown.append("crossing_signals")
    return tuple(dict.fromkeys(unknown))


def _scenario_weight(graph: nx.MultiDiGraph, u: Any, v: Any, data: dict, profile: Profile, scenario: str) -> float | None:
    """NetworkX-compatible weight, retaining MultiDiGraph parallel-edge semantics."""
    choices = []
    for key, edge in _edge_options(graph, data):
        if scenario == "documented" and critical_unknowns(edge, graph.nodes[u], graph.nodes[v], profile):
            continue
        value = _weight(graph, u, v, {key: edge}, profile, {})
        if value is not None:
            choices.append(value / SPEED_MPS[profile.value])
    return min(choices) if choices else None


def _feature(graph: nx.MultiDiGraph, u: Any, v: Any, key: Any, edge: dict, fraction: float = 1.0) -> dict | None:
    if fraction <= 0:
        return None
    coords = _edge_coords(graph, u, v, edge)
    line = LineString(coords) if fraction >= 1 else substring(LineString(coords), 0, fraction, normalized=True)
    if line.is_empty or line.geom_type != "LineString" or line.length <= 0:
        return None
    way_ids = _values(edge.get("osmid"))
    refs = [f"way/{way_id}" for way_id in way_ids]
    return {
        "type": "Feature",
        "id": json.dumps([str(u), str(v), str(key)], separators=(",", ":")),
        "geometry": mapping(line),
        "properties": {
            "from": str(u), "to": str(v), "key": str(key),
            "osm_way_ids": way_ids,
            "source_url": f"{SOURCE_OSM}{refs[0]}" if refs else None,
            "source_status": "SOURCE_DOCUMENTED",
        },
    }


def _example_path(graph: nx.MultiDiGraph, stop_node: Any, origin: Any, profile: Profile) -> dict | None:
    reverse = graph.reverse(copy=False)
    reverse_path = nx.shortest_path(
        reverse, stop_node, origin,
        weight=lambda v, u, data: _scenario_weight(graph, u, v, data, profile, "possible"),
    )
    path = list(reversed(reverse_path))
    coordinates: list[list[float]] = []
    source_refs: list[dict[str, Any]] = []
    for u, v in zip(path, path[1:]):
        choices = []
        for key, edge in _edge_options(graph, graph.get_edge_data(u, v)):
            weight = _scenario_weight(graph, u, v, {key: edge}, profile, "possible")
            if weight is not None:
                choices.append((weight, str(key), key, edge))
        if not choices:
            return None
        _, _, key, edge = min(choices, key=lambda item: (item[0], item[1]))
        segment = _edge_coords(graph, u, v, edge)
        coordinates.extend(segment if not coordinates else segment[1:])
        refs = _values(edge.get("osmid"))
        source_refs.extend({"osm_way_id": ref, "url": f"{SOURCE_OSM}way/{ref}"} for ref in refs[:1])
    if len(coordinates) < 2:
        return None
    return {
        "origin_node": str(origin),
        "time_seconds": None,
        "geometry": mapping(LineString(coordinates)),
        "source_refs": source_refs,
    }


class ReachabilityIndex:
    def __init__(self, graph: nx.MultiDiGraph, stops: list[dict[str, Any]], metadata: dict[str, Any], feed_info: list[dict[str, str]]):
        self.graph = graph
        self.metadata = metadata
        self.feed_info = feed_info
        self.nodes = {
            node for node, attrs in graph.nodes(data=True)
            if distance_m(CENTER, (float(attrs["y"]), float(attrs["x"]))) <= PILOT_RADIUS_M
        }
        self.stops = {
            str(stop["stop_id"]): stop for stop in stops
            if distance_m(CENTER, (float(stop["latitude"]), float(stop["longitude"]))) <= PILOT_RADIUS_M
        }

    def stop_list(self) -> list[dict[str, Any]]:
        return [
            {key: stop[key] for key in ("stop_id", "stop_name", "latitude", "longitude", "connector_distance_m")}
            for stop in sorted(self.stops.values(), key=lambda item: (item["stop_name"].casefold(), item["stop_id"]))
        ]

    def analyze(self, stop_id: str, profile: Profile = Profile.wheelchair, minutes: int = 10, sample_size: int = 150) -> dict[str, Any]:
        if profile.value not in {"standard", "wheelchair", "stroller", "low_vision"}:
            raise ValueError(f"Profile {profile.value!r} is not supported by this study")
        if not 1 <= minutes <= MAX_MINUTES:
            raise ValueError(f"Time budget must be between 1 and {MAX_MINUTES} minutes")
        if not 20 <= sample_size <= MAX_SAMPLE_SIZE:
            raise ValueError(f"Origin sample size must be between 20 and {MAX_SAMPLE_SIZE}")
        stop = self.stops.get(str(stop_id))
        if stop is None:
            raise KeyError(stop_id)
        try:
            connector_distance = float(stop.get("connector_distance_m", math.inf))
        except (TypeError, ValueError):
            connector_distance = math.inf
        if not math.isfinite(connector_distance) or connector_distance > MAX_STOP_CONNECTOR_M:
            return {
                "status": "STOP_CONNECTION_UNKNOWN",
                "stop": {key: stop[key] for key in ("stop_id", "stop_name", "latitude", "longitude", "connector_distance_m")},
                "message": f"The nearest mapped pedestrian node is more than {MAX_STOP_CONNECTOR_M} m from this GTFS stop. This study does not infer a path across that gap.",
                "warnings": [WARNING],
            }
        node = stop["graph_node"]
        if node not in self.graph and isinstance(node, str) and node.isdigit() and int(node) in self.graph:
            node = int(node)
        if node not in self.nodes:
            return {"status": "STOP_CONNECTION_UNKNOWN", "stop": {key: stop[key] for key in ("stop_id", "stop_name", "latitude", "longitude", "connector_distance_m")}, "message": "The GTFS stop node is outside the bounded Diridon study graph.", "warnings": [WARNING]}

        graph = nx.subgraph_view(self.graph, filter_node=self.nodes.__contains__)
        reverse = graph.reverse(copy=False)
        seconds = minutes * 60
        documented_dist = nx.single_source_dijkstra_path_length(
            reverse, node, cutoff=seconds,
            weight=lambda v, u, data: _scenario_weight(graph, u, v, data, profile, "documented"),
        )
        possible_dist = nx.single_source_dijkstra_path_length(
            reverse, node, cutoff=seconds,
            weight=lambda v, u, data: _scenario_weight(graph, u, v, data, profile, "possible"),
        )
        if not set(documented_dist).issubset(possible_dist):
            raise RuntimeError("Internal scenario invariant failed: documented graph reach is not a subset of possible reach")
        ordered_nodes = sorted((candidate for candidate in self.nodes if candidate != node), key=lambda item: sha256(f"{VERSION}:{item}".encode()).digest())[:sample_size]
        documented_origins = {sample for sample in ordered_nodes if documented_dist.get(sample, math.inf) <= seconds}
        possible_origins = {sample for sample in ordered_nodes if possible_dist.get(sample, math.inf) <= seconds}
        if not documented_origins.issubset(possible_origins):
            raise RuntimeError("Internal scenario invariant failed: documented reach is not a subset of possible reach")

        documented_features = []
        possible_features = []
        critical_unknown_count = 0
        unknown_examples = []
        crossing_unknown_examples = []
        for u, v, key, edge in graph.edges(keys=True, data=True):
            end_cost = possible_dist.get(v, math.inf)
            possible_weight = _scenario_weight(graph, u, v, {key: edge}, profile, "possible")
            if possible_weight is not None and end_cost < seconds:
                fraction = min(1.0, (seconds - end_cost) / possible_weight)
                feature = _feature(graph, u, v, key, edge, fraction)
                if feature:
                    possible_features.append(feature)
            doc_end_cost = documented_dist.get(v, math.inf)
            doc_weight = _scenario_weight(graph, u, v, {key: edge}, profile, "documented")
            if doc_weight is not None and doc_end_cost < seconds:
                fraction = min(1.0, (seconds - doc_end_cost) / doc_weight)
                feature = _feature(graph, u, v, key, edge, fraction)
                if feature:
                    documented_features.append(feature)
            missing = critical_unknowns(edge, graph.nodes[u], graph.nodes[v], profile)
            if missing and possible_weight is not None and end_cost < seconds:
                critical_unknown_count += 1
                if len(unknown_examples) < 8:
                    way_ids = _values(edge.get("osmid"))
                    for way_id in way_ids[:1]:
                        example = {"osm_way_id": way_id, "source_url": f"{SOURCE_OSM}way/{way_id}", "missing_critical_attributes": list(missing), "evidence_status": "UNKNOWN"}
                        if "crossing_kerb" in missing:
                            crossing_unknown_examples.append(example)
                        else:
                            unknown_examples.append(example)

        documented_refs = {feature["id"] for feature in documented_features}
        unknown_features = [feature for feature in possible_features if feature["id"] not in documented_refs]
        example_paths = []
        for origin in sorted(possible_origins, key=lambda item: sha256(f"{VERSION}:{item}".encode()).digest()):
            if origin == node:
                continue
            try:
                example = _example_path(graph, node, origin, profile)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue
            if example:
                example["time_seconds"] = round(possible_dist[origin], 1)
                example_paths.append(example)
            if len(example_paths) == 2:
                break
        status = "NO_SAMPLED_ORIGINS" if not ordered_nodes else "OK" if documented_origins else "INSUFFICIENT_DOCUMENTED_DATA"
        return {
            "status": status,
            "version": VERSION,
            "study_area": {"name": "Diridon Station pilot", "radius_m": PILOT_RADIUS_M, "center": {"latitude": CENTER[0], "longitude": CENTER[1]}},
            "stop": {key: stop[key] for key in ("stop_id", "stop_name", "latitude", "longitude", "connector_distance_m", "wheelchair_boarding") if key in stop},
            "gtfs_source": {"url": SOURCE_GTFS, "feed_info": self.feed_info},
            "osm_source": {"url": self.metadata.get("source_url") or SOURCE_OSM, "source_name": self.metadata.get("source", "OpenStreetMap"), "cache_file_modified_at": self.metadata.get("graph_modified_at"), "manifest_generated_at": self.metadata.get("manifest_generated_at"), "source_snapshot_date": self.metadata.get("source_snapshot_date"), "observation_timestamp": None},
            "profile": profile.value,
            "profile_assumptions": {"speed_mps": SPEED_MPS[profile.value], "time_budget_minutes": minutes, "maximum_stop_connector_m": MAX_STOP_CONNECTOR_M},
            "sampling": {"method": "Deterministic SHA-256 ordering of OSM node IDs; first N nodes; no population weighting", "origin_sample_count": len(ordered_nodes), "not_population_estimate": True},
            "documented": {"reachable_sample_origins": len(documented_origins), "reachable_graph_nodes": len(documented_dist), "reachable_edge_count": len(documented_features), "geometry": {"type": "FeatureCollection", "features": documented_features}},
            "possible": {"reachable_sample_origins": len(possible_origins), "reachable_graph_nodes": len(possible_dist), "reachable_edge_count": len(possible_features), "geometry": {"type": "FeatureCollection", "features": possible_features}},
            "unknown_gap": {"sample_origin_count": len(possible_origins - documented_origins), "edge_count": len(unknown_features), "critical_unknown_edge_count": critical_unknown_count, "geometry": {"type": "FeatureCollection", "features": unknown_features}, "examples": (crossing_unknown_examples + unknown_examples)[:8]},
            "example_paths": example_paths,
            "warnings": [WARNING, "Origin sampling is deterministic but not statistically representative.", "Missing fields are evaluated only for the documented predicates defined by this model; unmodeled conditions can still affect access."],
        }


def build_reachability_index(graph: nx.MultiDiGraph, stops: list[dict[str, Any]], metadata: dict[str, Any], feed_info: list[dict[str, str]]) -> ReachabilityIndex:
    """Create the bounded Diridon view from the currently loaded production graph."""
    return ReachabilityIndex(graph, stops, metadata, feed_info)
