"""Directed shortest paths and geometry reconstruction for OSM MultiDiGraphs."""

from __future__ import annotations

import json
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
from .geospatial import distance_m, nearest_graph_nodes
from .directions import accessibility_summary, describe_edge, directions as group_directions, geometry_audit

ACCESSIBILITY_WARNING = (
    "This route is not verified accessible. OpenStreetMap accessibility tags may be missing or out of date; "
    "unknown data does not mean accessible."
)
WALKING_SPEED_MPS = 1.2
MAX_SNAP_DISTANCE_M = 120.0
# The county graph is large enough that profile constraints can require more
# exploration than an ordinary A* trip. Keep a bound, but allow a realistic
# search window so longer wheelchair, stroller, and low-vision trips can finish.
ROUTE_SEARCH_LIMIT_SECONDS = 8.0
from .profiles import assess, evaluate, SPEED_MPS, OBJECTIVES

PROFILE_OBJECTIVES = {p: OBJECTIVES[p.value] for p in Profile}
haversine_m = distance_m


def _edge_options(
    graph: nx.MultiDiGraph, data: dict[str, Any]
) -> list[tuple[Any, dict[str, Any]]]:
    if (
        graph.is_multigraph()
        and data
        and all(isinstance(value, dict) for value in data.values())
    ):
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
        return sum(
            distance_m(
                (coords[i - 1][1], coords[i - 1][0]), (coords[i][1], coords[i][0])
            )
            for i in range(1, len(coords))
        )
    try:
        return distance_m(
            (float(graph.nodes[u]["y"]), float(graph.nodes[u]["x"])),
            (float(graph.nodes[v]["y"]), float(graph.nodes[v]["x"])),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"Edge {u!r}->{v!r} has no usable length or coordinates"
        ) from exc


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
                forward_gap = distance_m(
                    (coords[-1][1], coords[-1][0]),
                    (part_coords[0][1], part_coords[0][0]),
                )
                reverse_gap = distance_m(
                    (coords[-1][1], coords[-1][0]),
                    (part_coords[-1][1], part_coords[-1][0]),
                )
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
        raise ValueError(
            "Edge geometry contains coordinates outside longitude/latitude bounds"
        )
    return coords


def _report_extra(effects, u, v, key, profile):
    if not effects:return 0.0
    report=effects.get(json.dumps([str(u),str(v),str(key)],separators=(",",":")))
    if not report:return 0.0
    name="wheelchair" if profile.value=="avoid_mapped_stairs" else profile.value
    relevant=[r for r in report.get("reports",[report]) if name in r.get("affected_profiles",[])]
    if any(r["routing_effect"]=="block" for r in relevant):return None
    return {"wheelchair":1.5,"stroller":1.0,"low_vision":.5}.get(name,.2) if relevant else 0.0


def _best_edge(
    graph: nx.MultiDiGraph,
    u: Any,
    v: Any,
    profile: Profile,
    penalties: dict[str, float] | None = None,
    report_effects: dict | None = None,
) -> tuple[Any, dict[str, Any], float, float]:
    data = graph.get_edge_data(u, v)
    if not data:
        raise nx.NetworkXNoPath(f"No directed edge between {u!r} and {v!r}")
    start, end = graph.nodes[u], graph.nodes[v]
    if not node_public_access(start) or not node_public_access(end):
        raise nx.NetworkXNoPath(
            f"A graph node on {u!r}->{v!r} explicitly restricts pedestrian access"
        )
    candidates = []
    for insertion_order, (key, attrs) in enumerate(_edge_options(graph, data)):
        if (
            not _public_access(attrs)
            or not node_public_access(graph.nodes[u])
            or not node_public_access(graph.nodes[v])
        ):
            continue
        eligible, factor, *_ = evaluate(attrs, graph.nodes[u], graph.nodes[v], profile)
        if not eligible:
            continue
        length = _length_m(graph, u, v, attrs)
        penalty = (
            edge_uncertainty(attrs, start, end, profile, penalties)[0]
            if profile == Profile.prefer_documented_paths
            else 0.0
        )
        cost = length * (
            (1.0 + penalty) if profile == Profile.prefer_documented_paths else factor
        )
        extra = _report_extra(report_effects, u, v, key, profile)
        if extra is None:continue
        cost += length * extra
        if not isfinite(cost) or cost < 0:
            raise ValueError(f"Edge {u!r}->{v!r} has an invalid routing cost")
        candidates.append((cost, insertion_order, key, attrs, length, penalty))
    if not candidates:
        raise nx.NetworkXNoPath(f"No eligible directed edge between {u!r} and {v!r}")
    cost, _, key, attrs, length, penalty = min(
        candidates, key=lambda option: (option[0], option[1])
    )
    return key, attrs, length, penalty


def _weight(
    graph: nx.MultiDiGraph,
    u: Any,
    v: Any,
    data: dict[str, Any],
    profile: Profile,
    penalties: dict[str, float] | None = None,
    report_effects: dict | None = None,
) -> float | None:
    """NetworkX callback; for parallel arcs return their minimum eligible cost."""
    candidates = []
    for key, attrs in _edge_options(graph, data):
        if (
            not _public_access(attrs)
            or not node_public_access(graph.nodes[u])
            or not node_public_access(graph.nodes[v])
        ):
            continue
        eligible, factor, *_ = evaluate(attrs, graph.nodes[u], graph.nodes[v], profile)
        if not eligible:
            continue
        length = _length_m(graph, u, v, attrs)
        penalty = (
            edge_uncertainty(attrs, graph.nodes[u], graph.nodes[v], profile, penalties)[
                0
            ]
            if profile == Profile.prefer_documented_paths
            else 0.0
        )
        cost = length * (
            (1.0 + penalty) if profile == Profile.prefer_documented_paths else factor
        )
        extra = _report_extra(report_effects, u, v, key, profile)
        if extra is None:continue
        cost += length * extra
        if not isfinite(cost) or cost < 0:
            raise ValueError(f"Edge {u!r}->{v!r} has an invalid routing cost")
        candidates.append(cost)
    return min(candidates) if candidates else None


def _heuristic(graph: nx.MultiDiGraph, a: Any, b: Any) -> float:
    # Only the loaded immutable snapshot has a verified length/chord lower bound.
    # Uncertified/mutable input graphs use zero (A* becomes Dijkstra), so short
    # synthetic or malformed stored lengths cannot cause a suboptimal result.
    scale = graph.graph.get("transitgap_heuristic_scale", 0.0)
    return scale * distance_m(
        (float(graph.nodes[a]["y"]), float(graph.nodes[a]["x"])),
        (float(graph.nodes[b]["y"]), float(graph.nodes[b]["x"])),
    )


def _run(
    graph: nx.MultiDiGraph,
    start: Any,
    end: Any,
    algorithm: Algorithm,
    profile: Profile,
    penalties: dict[str, float] | None = None,
    report_effects: dict | None = None,
) -> tuple[list[Any], float]:
    """Run a real NetworkX algorithm against the same directed, profile-aware weights."""
    if start not in graph or end not in graph:
        raise nx.NodeNotFound(f"Origin or destination is not in the walking graph")
    if start == end:
        return [start], 0.0
    costs = {}
    search_started = perf_counter()

    def weight(u, v, data):
        key = (u, v)
        if key not in costs:
            if len(costs) % 256 == 0 and perf_counter() - search_started > ROUTE_SEARCH_LIMIT_SECONDS:
                raise ValueError(
                    f"Walking-network search exceeded its {ROUTE_SEARCH_LIMIT_SECONDS:g}-second limit. "
                    "Try moving the start to a nearby street entrance or choosing another stop."
                )
            costs[key] = _weight(graph, u, v, data, profile, penalties, report_effects)
        return costs[key]

    if algorithm == Algorithm.dijkstra:
        cost, path = nx.single_source_dijkstra(graph, start, end, weight=weight)
        return path, float(cost)
    if algorithm == Algorithm.bidirectional_dijkstra:
        cost, path = nx.bidirectional_dijkstra(graph, start, end, weight=weight)
        return path, float(cost)
    if algorithm in {Algorithm.bellman_ford, Algorithm.breadth_first}:
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
                for neighbor in graph.successors(current):
                    edge_cost = weight(
                        current, neighbor, graph.get_edge_data(current, neighbor)
                    )
                    if edge_cost is None:
                        continue
                    candidate = distances[current] + edge_cost
                    if candidate < distances.get(
                        neighbor, float("inf")
                    ) and candidate <= distances.get(end, float("inf")):
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
            for neighbor in graph.successors(current):
                if (
                    neighbor not in parents
                    and weight(
                        current, neighbor, graph.get_edge_data(current, neighbor)
                    )
                    is not None
                ):
                    parents[neighbor] = current
                    queue.append(neighbor)
        if end not in parents:
            raise nx.NetworkXNoPath("No eligible walking-network path")
        path = [end]
        while path[-1] != start:
            path.append(parents[path[-1]])
        path.reverse()
        cost = sum(
            weight(u, v, graph.get_edge_data(u, v)) for u, v in zip(path, path[1:])
        )
        return path, float(cost)
    path = nx.astar_path(
        graph, start, end, heuristic=lambda a, b: _heuristic(graph, a, b), weight=weight
    )
    cost = sum(
        weight(u, v, graph.get_edge_data(u, v))
        for u, v in zip(path, path[1:])
    )
    return path, float(cost)


def _edge_coords(
    graph: nx.MultiDiGraph, u: Any, v: Any, attrs: dict[str, Any]
) -> list[list[float]]:
    coords = _geometry_coords(attrs.get("geometry"))
    start = [float(graph.nodes[u]["x"]), float(graph.nodes[u]["y"])]
    end = [float(graph.nodes[v]["x"]), float(graph.nodes[v]["y"])]
    if len(coords) < 2:
        if attrs.get("geometry") is not None:
            raise ValueError(f"Edge {u!r}->{v!r} has invalid stored geometry")
        return [start, end]
    forward = distance_m(
        (coords[0][1], coords[0][0]), (start[1], start[0])
    ) + distance_m((coords[-1][1], coords[-1][0]), (end[1], end[0]))
    reverse = distance_m(
        (coords[-1][1], coords[-1][0]), (start[1], start[0])
    ) + distance_m((coords[0][1], coords[0][0]), (end[1], end[0]))
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


def calculate_route(
    graph: nx.MultiDiGraph,
    origin: tuple[float, float],
    destination_node: Any,
    algorithm: Algorithm,
    profile: Profile,
    stop: dict[str, Any],
    report_effects: dict | None = None,
) -> dict[str, Any]:
    started = perf_counter()
    lat, lon = map(float, origin)
    if (
        not isfinite(lat)
        or not isfinite(lon)
        or not -90 <= lat <= 90
        or not -180 <= lon <= 180
    ):
        raise ValueError(
            "Starting coordinates must be finite latitude and longitude values"
        )
    if graph.number_of_nodes() == 0:
        raise LookupError("The mapped walking network is empty.")
    penalties = (
        uncertainty_penalties() if profile == Profile.prefer_documented_paths else {}
    )
    if (
        destination_node not in graph
        and isinstance(destination_node, str)
        and destination_node.isdigit()
    ):
        destination_node = int(destination_node)
    targets = [destination_node]
    candidates = [
        (node, distance)
        for node, distance in nearest_graph_nodes(graph, lat, lon, count=24)
        if distance <= MAX_SNAP_DISTANCE_M
    ]
    if not candidates:
        _, snap_distance = nearest_graph_nodes(graph, lat, lon, count=1)[0]
        raise ValueError(
            f"Starting point is {round(snap_distance)} m from a mapped walking path; "
            f"the limit is {MAX_SNAP_DISTANCE_M:g} m. Move the pin closer to a street or sidewalk."
        )

    # A pin may land inside a building or on an isolated mapped feature. Check
    # nearby nodes against the destination's connected component before running
    # an expensive full-network search. The checks are bounded: prefer a
    # confirmed directed connection, remembering the nearest inconclusive
    # candidate as a fallback. Directionality and mobility rules still come
    # from the selected routing algorithm below.
    def reaches_target(start: Any, *, directed: bool, limit: int = 4096) -> bool | None:
        if start in targets:
            return True
        seen = {start}
        queue = deque([start])
        while queue:
            current = queue.popleft()
            neighbors = set(graph.successors(current))
            if not directed:
                neighbors.update(graph.predecessors(current))
            for neighbor in neighbors:
                if neighbor in targets:
                    return True
                if neighbor not in seen:
                    seen.add(neighbor)
                    if len(seen) >= limit:
                        return None
                    queue.append(neighbor)
        return False

    eligible = []
    uncertain = None
    for candidate, snap_distance in candidates:
        weak = reaches_target(candidate, directed=False)
        if weak is False:
            continue
        if weak is None:
            uncertain = uncertain or (candidate, snap_distance)
            continue
        directed = reaches_target(candidate, directed=True)
        if directed is False:
            continue
        if directed is None:
            uncertain = uncertain or (candidate, snap_distance)
            continue
        eligible.append((candidate, snap_distance))
        # Prefer the closest candidate with a confirmed directed connection.
        break
    if not eligible and uncertain:
        # No nearby candidate had a connection that the bounded probes could
        # confirm. Preserve best-effort routing from the nearest plausible node.
        eligible.append(uncertain)
    if not eligible:
        raise LookupError(
            "This start is not connected to the mapped walking route for this stop. "
            "Move the pin to a nearby street or sidewalk entrance, then try again."
        )
    nearest, snap_distance = eligible[0]
    try:
        nodes, optimization_edge_cost = _run(
            graph, nearest, destination_node, algorithm, profile, penalties, report_effects
        )
    except (nx.NodeNotFound, nx.NetworkXNoPath) as exc:
        raise LookupError(
            "No mapped walking route connects this start and stop for the chosen profile. "
            "Try a nearby street entrance or another stop."
        ) from exc

    coords: list[list[float]] = []
    segments = []
    physical_edge_distance = 0.0
    mapped_stair_segments = 0
    selected_edge_keys = []
    public_segments = []
    tagged_distance = 0.0
    for u, v in zip(nodes, nodes[1:]):
        key, attrs, length, penalty = _best_edge(graph, u, v, profile, penalties, report_effects)
        segment_coords = _edge_coords(graph, u, v, attrs)
        if coords and coords[-1] != segment_coords[0]:
            if (
                distance_m(
                    (coords[-1][1], coords[-1][0]),
                    (segment_coords[0][1], segment_coords[0][0]),
                )
                > 0.01
            ):
                raise ValueError(
                    "Selected OSM route edges do not join at their shared graph node"
                )
        coords.extend(segment_coords if not coords else segment_coords[1:])
        physical_edge_distance += length
        mapped_stair_segments += int(is_mapped_stairs(attrs))
        selected_edge_keys.append(
            {"from": str(u), "to": str(v), "key": str(key) if key is not None else None, "reference": json.dumps([str(u),str(v),str(key)],separators=(",",":"))}
        )
        _, _, status, reasons, known = evaluate(
            attrs, graph.nodes[u], graph.nodes[v], profile
        )
        # Fraction of applicable fields documented, weighted by segment length.
        missing_count = sum(r.startswith("Missing ") for r in reasons)
        tagged_distance += length * len(known) / max(1, len(known) + missing_count)
        name = attrs.get("name")
        if isinstance(name, list):
            name = " / ".join(str(n) for n in name)
        public_segments.append(
            {
                "geometry": mapping(LineString(segment_coords)),
                "length_m": round(length, 2),
                "status": status,
                "reasons": reasons,
                "name": name,
                "costs": ({"physical_distance_m":length,"difficulty_cost_m":0,"uncertainty_cost_m":length*penalty,"optimization_cost_m":length*(1+penalty)} if profile == Profile.prefer_documented_paths else assess(attrs, graph.nodes[u], graph.nodes[v], profile).costs(length)),
                "documented_attributes": known,
                "missing_attributes": list(assess(attrs, graph.nodes[u], graph.nodes[v], profile).missing),
                "source": "OpenStreetMap; mapped, not field checked",
                "osm_id": attrs.get("osmid"),
                **describe_edge(attrs, graph.nodes[u], graph.nodes[v]),
                "end_junction_degree": _junction_degree(graph, v),
            }
        )
        segments.append(
            {
                "data": attrs,
                "start": graph.nodes[u],
                "end": graph.nodes[v],
                "start_id": str(u),
                "end_id": str(v),
                "length_m": length,
                "key": key,
            }
        )

    if not coords:
        coords = [[float(graph.nodes[nearest]["x"]), float(graph.nodes[nearest]["y"])]]
    origin_xy = [lon, lat]
    stop_xy = [float(stop["longitude"]), float(stop["latitude"])]
    origin_connector = distance_m((lat, lon), (coords[0][1], coords[0][0]))
    stop_connector = distance_m(
        (coords[-1][1], coords[-1][0]), (stop_xy[1], stop_xy[0])
    )
    if origin_connector > 0.01:
        coords.insert(0, origin_xy)
    if stop_connector > 0.01:
        coords.append(stop_xy)
    connector_distance = origin_connector + stop_connector
    physical_distance = physical_edge_distance + connector_distance
    for points, length in (
        (
            [
                origin_xy,
                [float(graph.nodes[nearest]["x"]), float(graph.nodes[nearest]["y"])],
            ],
            origin_connector,
        ),
        (
            [
                [
                    float(graph.nodes[destination_node]["x"]),
                    float(graph.nodes[destination_node]["y"]),
                ],
                stop_xy,
            ],
            stop_connector,
        ),
    ):
        if length > 0.01:
            connector = {
                "geometry": mapping(LineString(points)),
                "length_m": round(length, 2),
                "status": "unknown",
                "reasons": ["Off-network connector; path not assessed"],
                "name": None,
                "source": "Straight-line connector, not a mapped sidewalk",
                "kind": "connector",
            }
            public_segments.insert(0, connector) if points[
                0
            ] == origin_xy else public_segments.append(connector)
    total_cost = float(optimization_edge_cost) + connector_distance
    if len(coords) == 1:
        coords.append(coords[0].copy())
    geometry = mapping(LineString(coords))
    accessibility = analyze_route(segments, connector_distance)
    accessibility["selected_edge_keys"] = selected_edge_keys
    accessibility["uncertainty_penalty_weights"] = (
        penalties if profile == Profile.prefer_documented_paths else None
    )
    destination_info = {
        key: stop[key] for key in ("stop_id", "stop_name", "latitude", "longitude", "agency", "agency_name") if key in stop
    }
    maneuvers = group_directions(public_segments, destination_info)
    return {
        "geometry": geometry,
        "distance_m": round(physical_distance, 1),
        "duration_seconds": round(physical_distance / SPEED_MPS[profile.value]),
        "walking_speed_mps_assumed": SPEED_MPS[profile.value],
        "selected_edges": selected_edge_keys,
        "segments": public_segments,
        "data_confidence": round(tagged_distance / physical_distance, 4)
        if physical_distance
        else None,
        "data_confidence_definition": "Length-weighted share of applicable attributes documented in OSM; not verified accessibility",
        "directions": maneuvers,
        "accessibility_summary": accessibility_summary(public_segments, maneuvers, physical_distance),
        "geometry_audit": geometry_audit(public_segments),
        "algorithm": algorithm.value,
        "profile": profile.value,
        "optimization_objective": (
            "Minimize eligible walking-network segments; distance is not minimized"
            if algorithm == Algorithm.breadth_first
            else PROFILE_OBJECTIVES[profile]
        ),
        "optimization_hops": len(nodes) - 1,
        "algorithm_warning": (
            "Breadth-first search finds the fewest network segments. It can produce a longer walk."
            if algorithm == Algorithm.breadth_first
            else None
        ),
        "optimization_cost_m": round(total_cost, 3),
        "uncertainty_cost_m": round(total_cost - physical_distance, 3),
        "computation_time_ms": round((perf_counter() - started) * 1000, 2),
        "graph_nodes_traversed": len(nodes),
        "mapped_stair_segments": mapped_stair_segments,
        "accessibility": accessibility,
        "accessibility_warning": ACCESSIBILITY_WARNING,
        "destination": destination_info,
    }


def _junction_degree(graph: nx.MultiDiGraph, node: Any) -> int:
    """Distinct mapped neighbours of a node, ignoring edge direction."""
    return len((set(graph.successors(node)) | set(graph.predecessors(node))) - {node})


def directions(segments, destination=None):
    """Grouped rider-facing maneuvers; see directions.py for the rules."""
    return group_directions(segments, destination)
