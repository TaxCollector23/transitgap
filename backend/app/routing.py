"""Directed shortest paths and geometry reconstruction for OSM MultiDiGraphs."""
from __future__ import annotations

from math import isfinite
from time import perf_counter
from typing import Any
from collections import deque

import networkx as nx
from shapely.geometry import LineString, mapping
from shapely import wkt

from .accessibility import (
    _public_access,
    analyze_route,
    edge_uncertainty,
    is_mapped_stairs,
    node_public_access,
    uncertainty_penalties,
)
from .models import Algorithm, Profile
from .geospatial import distance_m, nearest_graph_node

ACCESSIBILITY_WARNING = (
    "This route is not verified accessible. OpenStreetMap accessibility tags may be missing or out of date; "
    "unknown data does not mean accessible."
)
WALKING_SPEED_MPS = 1.2
MAX_SNAP_DISTANCE_M = 120.0
PROFILE_OBJECTIVES = {
    Profile.standard: "Minimize walking distance",
    Profile.avoid_mapped_stairs: "Minimize walking distance while excluding explicitly mapped stair edges",
    Profile.prefer_documented_paths: "Minimize walking distance weighted by missing applicable OpenStreetMap attributes",
}
haversine_m = distance_m


def _edge_options(graph: nx.MultiDiGraph, data: dict[str, Any]) -> list[tuple[Any, dict[str, Any]]]:
    if graph.is_multigraph() and data and all(isinstance(value, dict) for value in data.values()):
        return list(data.items())
    return [(None, data)]


def _length_m(graph: nx.MultiDiGraph, u: Any, v: Any, attrs: dict[str, Any]) -> float:
    raw = attrs.get("length")
    if raw is not None:
        length = float(raw)
        if not isfinite(length) or length < 0:
            raise ValueError(f"Edge {u!r}->{v!r} has an invalid or negative length")
        return length
    coords = _geometry_coords(attrs.get("geometry"))
    if attrs.get("geometry") is not None and len(coords) < 2:
        raise ValueError(f"Edge {u!r}->{v!r} has invalid stored geometry")
    if len(coords) >= 2:
        return sum(distance_m((coords[i - 1][1], coords[i - 1][0]), (coords[i][1], coords[i][0]))
                   for i in range(1, len(coords)))
    try:
        return distance_m((float(graph.nodes[u]["y"]), float(graph.nodes[u]["x"])),
                           (float(graph.nodes[v]["y"]), float(graph.nodes[v]["x"])))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Edge {u!r}->{v!r} has no usable length or coordinates") from exc


def _geometry_coords(raw: Any) -> list[list[float]]:
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = wkt.loads(raw)
        except Exception as exc:
            raise ValueError("Edge geometry is not valid WKT") from exc
    try:
        parts = list(raw.geoms) if hasattr(raw, "geoms") else [raw]
        coords = []
        for part in parts:
            part_coords = [[float(x), float(y)] for x, y, *_ in part.coords]
            if not part_coords:
                continue
            if coords:
                forward_gap = distance_m((coords[-1][1], coords[-1][0]), (part_coords[0][1], part_coords[0][0]))
                reverse_gap = distance_m((coords[-1][1], coords[-1][0]), (part_coords[-1][1], part_coords[-1][0]))
                if reverse_gap < forward_gap:
                    part_coords.reverse()
                    forward_gap = reverse_gap
                if forward_gap > 2.0:
                    raise ValueError("Edge geometry has disconnected components")
                part_coords = part_coords[1:]
            coords.extend(part_coords)
    except (AttributeError, TypeError, NotImplementedError):
        try:
            coords = [[float(x), float(y)] for x, y, *_ in raw]
        except (TypeError, ValueError) as exc:
            raise ValueError("Edge geometry cannot be read as coordinates") from exc
    if not all(isfinite(value) for point in coords for value in point):
        raise ValueError("Edge geometry contains nonfinite coordinates")
    if any(not -180 <= x <= 180 or not -90 <= y <= 90 for x, y in coords):
        raise ValueError("Edge geometry contains coordinates outside longitude/latitude bounds")
    return coords


def _best_edge(graph: nx.MultiDiGraph, u: Any, v: Any, profile: Profile,
               penalties: dict[str, float] | None = None) -> tuple[Any, dict[str, Any], float, float]:
    data = graph.get_edge_data(u, v)
    if not data:
        raise nx.NetworkXNoPath(f"No directed edge between {u!r} and {v!r}")
    start, end = graph.nodes[u], graph.nodes[v]
    if not node_public_access(start) or not node_public_access(end):
        raise nx.NetworkXNoPath(f"A graph node on {u!r}->{v!r} explicitly restricts pedestrian access")
    candidates = []
    for insertion_order, (key, attrs) in enumerate(_edge_options(graph, data)):
        if not _public_access(attrs) or not node_public_access(graph.nodes[u]) or not node_public_access(graph.nodes[v]):
            continue
        if profile == Profile.avoid_mapped_stairs and is_mapped_stairs(attrs):
            continue
        length = _length_m(graph, u, v, attrs)
        penalty = edge_uncertainty(attrs, start, end, profile, penalties)[0] if profile == Profile.prefer_documented_paths else 0.0
        cost = length * (1.0 + penalty)
        if not isfinite(cost) or cost < 0:
            raise ValueError(f"Edge {u!r}->{v!r} has an invalid routing cost")
        candidates.append((cost, insertion_order, key, attrs, length, penalty))
    if not candidates:
        raise nx.NetworkXNoPath(f"No eligible directed edge between {u!r} and {v!r}")
    cost, _, key, attrs, length, penalty = min(candidates, key=lambda option: (option[0], option[1]))
    return key, attrs, length, penalty


def _weight(graph: nx.MultiDiGraph, u: Any, v: Any, data: dict[str, Any], profile: Profile,
            penalties: dict[str, float] | None = None) -> float | None:
    """NetworkX callback; for parallel arcs return their minimum eligible cost."""
    candidates = []
    for _, attrs in _edge_options(graph, data):
        if not _public_access(attrs) or not node_public_access(graph.nodes[u]) or not node_public_access(graph.nodes[v]):
            continue
        if profile == Profile.avoid_mapped_stairs and is_mapped_stairs(attrs):
            continue
        length = _length_m(graph, u, v, attrs)
        penalty = edge_uncertainty(attrs, graph.nodes[u], graph.nodes[v], profile, penalties)[0] if profile == Profile.prefer_documented_paths else 0.0
        cost = length * (1.0 + penalty)
        if not isfinite(cost) or cost < 0:
            raise ValueError(f"Edge {u!r}->{v!r} has an invalid routing cost")
        candidates.append(cost)
    return min(candidates) if candidates else None


def _heuristic(graph: nx.MultiDiGraph, a: Any, b: Any) -> float:
    # Every optimization edge costs length * (1 + nonnegative penalty), so this
    # straight-line physical distance is admissible for every supported profile.
    return distance_m((float(graph.nodes[a]["y"]), float(graph.nodes[a]["x"])),
                       (float(graph.nodes[b]["y"]), float(graph.nodes[b]["x"])))


def _run(graph: nx.MultiDiGraph, start: Any, end: Any, algorithm: Algorithm,
         profile: Profile, penalties: dict[str, float] | None = None) -> tuple[list[Any], float]:
    """Run a real NetworkX algorithm against the same directed, profile-aware weights."""
    if start not in graph or end not in graph:
        raise nx.NodeNotFound(f"Origin or destination is not in the walking graph")
    if start == end:
        return [start], 0.0
    weight = lambda u, v, data: _weight(graph, u, v, data, profile, penalties)
    if algorithm == Algorithm.dijkstra:
        cost, path = nx.single_source_dijkstra(graph, start, end, weight=weight)
        return path, float(cost)
    if algorithm == Algorithm.bidirectional_dijkstra:
        cost, path = nx.bidirectional_dijkstra(graph, start, end, weight=weight)
        return path, float(cost)
    if algorithm in {Algorithm.bellman_ford, Algorithm.breadth_first}:
        if graph.is_multigraph():
            eligible = nx.subgraph_view(graph, filter_edge=lambda u, v, key:
                _weight(graph, u, v, {key: graph[u][v][key]}, profile, penalties) is not None)
        else:
            eligible = nx.subgraph_view(graph, filter_edge=lambda u, v:
                _weight(graph, u, v, graph[u][v], profile, penalties) is not None)
        if algorithm == Algorithm.bellman_ford:
            # Queue-based Bellman–Ford (SPFA). Costs in this service are
            # nonnegative, so a known target cost safely bounds further work.
            distances = {start: 0.0}
            parents = {start: None}
            queue = deque([start])
            queued = {start}
            while queue:
                current = queue.popleft()
                queued.remove(current)
                if distances[current] >= distances.get(end, float("inf")):
                    continue
                for neighbor in eligible.successors(current):
                    candidate = distances[current] + weight(current, neighbor, graph.get_edge_data(current, neighbor))
                    if candidate < distances.get(neighbor, float("inf")) and candidate <= distances.get(end, float("inf")):
                        distances[neighbor] = candidate
                        parents[neighbor] = current
                        if neighbor != end and neighbor not in queued:
                            queue.append(neighbor)
                            queued.add(neighbor)
            if end not in parents:
                raise nx.NetworkXNoPath("No eligible walking-network path")
            path = [end]
            while path[-1] != start:
                path.append(parents[path[-1]])
            path.reverse()
            return path, float(distances[end])
        parents = {start: None}
        queue = deque([start])
        while queue and end not in parents:
            current = queue.popleft()
            for neighbor in eligible.successors(current):
                if neighbor not in parents:
                    parents[neighbor] = current
                    queue.append(neighbor)
        if end not in parents:
            raise nx.NetworkXNoPath("No eligible walking-network path")
        path = [end]
        while path[-1] != start:
            path.append(parents[path[-1]])
        path.reverse()
        cost = sum(weight(u, v, graph.get_edge_data(u, v)) for u, v in zip(path, path[1:]))
        return path, float(cost)
    path = nx.astar_path(graph, start, end, heuristic=lambda a, b: _heuristic(graph, a, b), weight=weight)
    cost = sum(_weight(graph, u, v, graph.get_edge_data(u, v), profile, penalties)
               for u, v in zip(path, path[1:]))
    return path, float(cost)


def _edge_coords(graph: nx.MultiDiGraph, u: Any, v: Any, attrs: dict[str, Any]) -> list[list[float]]:
    coords = _geometry_coords(attrs.get("geometry"))
    start = [float(graph.nodes[u]["x"]), float(graph.nodes[u]["y"])]
    end = [float(graph.nodes[v]["x"]), float(graph.nodes[v]["y"])]
    if len(coords) < 2:
        if attrs.get("geometry") is not None:
            raise ValueError(f"Edge {u!r}->{v!r} has invalid stored geometry")
        return [start, end]
    forward = distance_m((coords[0][1], coords[0][0]), (start[1], start[0])) + distance_m((coords[-1][1], coords[-1][0]), (end[1], end[0]))
    reverse = distance_m((coords[-1][1], coords[-1][0]), (start[1], start[0])) + distance_m((coords[0][1], coords[0][0]), (end[1], end[0]))
    if reverse < forward:
        coords.reverse()
    # OSMnx simplified edge geometries normally start and end at their graph
    # nodes. Repair small serialization rounding gaps, but reject larger gaps
    # instead of drawing an unmeasured straight-line shortcut.
    start_gap = distance_m((coords[0][1], coords[0][0]), (start[1], start[0]))
    end_gap = distance_m((coords[-1][1], coords[-1][0]), (end[1], end[0]))
    if start_gap > 2.0 or end_gap > 2.0:
        raise ValueError("OSM edge geometry does not meet its graph-node endpoints")
    coords[0] = start
    coords[-1] = end
    return coords


def calculate_route(graph: nx.MultiDiGraph, origin: tuple[float, float], destination_node: Any,
                    algorithm: Algorithm, profile: Profile, stop: dict[str, Any]) -> dict[str, Any]:
    started = perf_counter()
    lat, lon = map(float, origin)
    if not isfinite(lat) or not isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("Starting coordinates must be finite latitude and longitude values")
    if graph.number_of_nodes() == 0:
        raise LookupError("The mapped walking network is empty.")
    penalties = uncertainty_penalties() if profile == Profile.prefer_documented_paths else {}
    # Search the complete graph. Selecting the largest component can snap a
    # nearby origin to a distant component and makes legitimate isolated paths
    # impossible to route. The selected component is instead handled naturally
    # by the directed shortest-path search below.
    nearest, snap_distance = nearest_graph_node(graph, lat, lon)
    if snap_distance > MAX_SNAP_DISTANCE_M:
        raise ValueError(f"Starting point is {round(snap_distance)} m from the walk network; choose a point within {MAX_SNAP_DISTANCE_M:g} m of a mapped path.")
    if destination_node not in graph and isinstance(destination_node, str) and destination_node.isdigit():
        destination_node = int(destination_node)
    try:
        nodes, optimization_edge_cost = _run(graph, nearest, destination_node, algorithm, profile, penalties)
    except (nx.NodeNotFound, nx.NetworkXNoPath) as exc:
        raise LookupError("No walking route connects this starting point to the selected stop with the chosen profile.") from exc

    coords: list[list[float]] = []
    segments = []
    physical_edge_distance = 0.0
    mapped_stair_segments = 0
    selected_edge_keys = []
    for u, v in zip(nodes, nodes[1:]):
        key, attrs, length, penalty = _best_edge(graph, u, v, profile, penalties)
        segment_coords = _edge_coords(graph, u, v, attrs)
        if coords and coords[-1] != segment_coords[0]:
            if distance_m((coords[-1][1], coords[-1][0]), (segment_coords[0][1], segment_coords[0][0])) > 0.01:
                raise ValueError("Selected OSM route edges do not join at their shared graph node")
        coords.extend(segment_coords if not coords else segment_coords[1:])
        physical_edge_distance += length
        mapped_stair_segments += int(is_mapped_stairs(attrs))
        selected_edge_keys.append({"from": str(u), "to": str(v), "key": str(key) if key is not None else None})
        segments.append({"data": attrs, "start": graph.nodes[u], "end": graph.nodes[v],
                         "start_id": str(u), "end_id": str(v), "length_m": length, "key": key})

    if not coords:
        coords = [[float(graph.nodes[nearest]["x"]), float(graph.nodes[nearest]["y"])]]
    origin_xy = [lon, lat]
    stop_xy = [float(stop["longitude"]), float(stop["latitude"])]
    origin_connector = distance_m((lat, lon), (coords[0][1], coords[0][0]))
    stop_connector = distance_m((coords[-1][1], coords[-1][0]), (stop_xy[1], stop_xy[0]))
    if origin_connector > 0.01:
        coords.insert(0, origin_xy)
    if stop_connector > 0.01:
        coords.append(stop_xy)
    connector_distance = origin_connector + stop_connector
    physical_distance = physical_edge_distance + connector_distance
    total_cost = float(optimization_edge_cost) + connector_distance
    if len(coords) == 1:
        coords.append(coords[0].copy())
    geometry = mapping(LineString(coords))
    accessibility = analyze_route(segments, connector_distance)
    accessibility["selected_edge_keys"] = selected_edge_keys
    accessibility["uncertainty_penalty_weights"] = penalties if profile == Profile.prefer_documented_paths else None
    return {
        "geometry": geometry,
        "distance_m": round(physical_distance, 1),
        "duration_seconds": round(physical_distance / WALKING_SPEED_MPS),
        "walking_speed_mps_assumed": WALKING_SPEED_MPS,
        "algorithm": algorithm.value,
        "profile": profile.value,
        "optimization_objective": ("Minimize eligible walking-network segments; distance is not minimized"
                                   if algorithm == Algorithm.breadth_first else PROFILE_OBJECTIVES[profile]),
        "optimization_hops": len(nodes) - 1,
        "algorithm_warning": ("Breadth-first search finds the fewest network segments. It can produce a longer walk."
                              if algorithm == Algorithm.breadth_first else None),
        "optimization_cost_m": round(total_cost, 3),
        "uncertainty_cost_m": round(total_cost - physical_distance, 3),
        "computation_time_ms": round((perf_counter() - started) * 1000, 2),
        "graph_nodes_traversed": len(nodes),
        "mapped_stair_segments": mapped_stair_segments,
        "accessibility": accessibility,
        "accessibility_warning": ACCESSIBILITY_WARNING,
        "destination": {key: stop[key] for key in ("stop_id", "stop_name", "latitude", "longitude")},
    }
