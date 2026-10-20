from __future__ import annotations
from math import radians, sin, cos, asin, sqrt, hypot
from time import perf_counter
from typing import Any
import networkx as nx
from shapely.geometry import LineString, mapping
from .models import Algorithm, Profile

ACCESSIBILITY_WARNING = "This route is not verified accessible. OSM accessibility tags may be missing or out of date; unknown data does not mean accessible."
WALKING_SPEED_MPS = 1.2
MAX_SNAP_DISTANCE_M = 120

def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(radians, a); lat2, lon2 = map(radians, b)
    dlat, dlon = lat2-lat1, lon2-lon1
    h = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return 6371000 * 2 * asin(sqrt(h))

def _tag_values(value: Any) -> set[str]:
    if value is None: return set()
    if isinstance(value, (list, tuple, set)): return {str(x).strip().lower() for x in value}
    return {part.strip().lower() for part in str(value).replace(";", ",").split(",")}

def is_mapped_stairs(data: dict[str, Any]) -> bool:
    return "steps" in _tag_values(data.get("highway")) or "steps" in _tag_values(data.get("footway")) or "steps" in _tag_values(data.get("indoor"))

def _weight(graph: nx.MultiDiGraph, u: Any, v: Any, data: dict[str, Any], profile: Profile) -> float | None:
    candidates = [attrs for attrs in data.values()] if graph.is_multigraph() and data and all(isinstance(vv, dict) for vv in data.values()) else [data]
    allowed = [attrs for attrs in candidates if not (profile == Profile.avoid_mapped_stairs and is_mapped_stairs(attrs))]
    if not allowed: return None
    return min(max(0.0, float(attrs.get("length", 0.0))) for attrs in allowed)

def _heuristic(graph: nx.MultiDiGraph, a: Any, b: Any) -> float:
    return haversine_m((float(graph.nodes[a]["y"]), float(graph.nodes[a]["x"])), (float(graph.nodes[b]["y"]), float(graph.nodes[b]["x"])))

def _run(graph: nx.MultiDiGraph, start: Any, end: Any, algorithm: Algorithm, profile: Profile) -> tuple[list[Any], float]:
    weight = lambda u,v,d: _weight(graph,u,v,d,profile)
    if algorithm == Algorithm.dijkstra:
        distance, path = nx.single_source_dijkstra(graph, start, end, weight=weight)
        return path, distance
    if algorithm == Algorithm.bidirectional_dijkstra:
        distance, path = nx.bidirectional_dijkstra(graph, start, end, weight=weight)
        return path, distance
    path = nx.astar_path(graph, start, end, heuristic=lambda a,b:_heuristic(graph,a,b), weight=weight)
    distance = sum(weight(u, v, graph.get_edge_data(u, v)) for u, v in zip(path, path[1:]))
    return path, distance

def _edge_data(graph: nx.MultiDiGraph, u: Any, v: Any, profile: Profile) -> dict[str, Any]:
    keyed = graph.get_edge_data(u,v) or {}
    options = list(keyed.values()) if graph.is_multigraph() else [keyed]
    options = [d for d in options if not (profile == Profile.avoid_mapped_stairs and is_mapped_stairs(d))]
    if not options: raise nx.NetworkXNoPath(f"No eligible edge between {u} and {v}")
    return min(options, key=lambda d: float(d.get("length",0)))

def _edge_coords(graph: nx.MultiDiGraph, u: Any, v: Any, attrs: dict[str, Any]) -> list[list[float]]:
    raw = attrs.get("geometry")
    coords = []
    if raw is not None:
        try: coords = [[float(x),float(y)] for x,y in raw.coords]
        except AttributeError: pass
        except Exception: coords = []
    if len(coords) < 2:
        coords = [[float(graph.nodes[u]["x"]),float(graph.nodes[u]["y"])],[float(graph.nodes[v]["x"]),float(graph.nodes[v]["y"])]]
    start = [float(graph.nodes[u]["x"]),float(graph.nodes[u]["y"])]; end = [float(graph.nodes[v]["x"]),float(graph.nodes[v]["y"])]
    if hypot(coords[0][0]-start[0],coords[0][1]-start[1]) + hypot(coords[-1][0]-end[0],coords[-1][1]-end[1]) > hypot(coords[-1][0]-start[0],coords[-1][1]-start[1]) + hypot(coords[0][0]-end[0],coords[0][1]-end[1]): coords.reverse()
    return coords

def calculate_route(graph: nx.MultiDiGraph, origin: tuple[float,float], destination_node: Any, algorithm: Algorithm, profile: Profile, stop: dict[str,Any]) -> dict[str,Any]:
    started = perf_counter()
    connected = max(nx.weakly_connected_components(graph), key=len)
    nearest = min(connected, key=lambda n:haversine_m(origin,(float(graph.nodes[n]["y"]),float(graph.nodes[n]["x"]))))
    snap_distance = haversine_m(origin,(float(graph.nodes[nearest]["y"]),float(graph.nodes[nearest]["x"])))
    if snap_distance > MAX_SNAP_DISTANCE_M: raise ValueError(f"Starting point is {round(snap_distance)} m from the walk network; choose a point within {MAX_SNAP_DISTANCE_M} m of a mapped street.")
    destination_node = int(destination_node) if isinstance(destination_node,str) and destination_node.isdigit() else destination_node
    try: nodes, _ = _run(graph,nearest,destination_node,algorithm,profile)
    except (nx.NodeNotFound,nx.NetworkXNoPath) as exc: raise LookupError("No walking route connects this starting point to the selected stop with the chosen profile.") from exc
    coords: list[list[float]] = []
    distance = 0.0; stair_count = 0
    for u,v in zip(nodes,nodes[1:]):
        attrs = _edge_data(graph,u,v,profile)
        segment = _edge_coords(graph,u,v,attrs)
        coords.extend(segment if not coords else segment[1:])
        distance += float(attrs.get("length",0.0))
        if is_mapped_stairs(attrs): stair_count += 1
    if len(nodes) == 1: coords = [[float(graph.nodes[nearest]["x"]),float(graph.nodes[nearest]["y"])]]
    # Include the true selected origin and actual transit stop location as short connector geometry.
    start_xy = [origin[1],origin[0]]; stop_xy=[float(stop["longitude"]),float(stop["latitude"])]
    if coords and start_xy != coords[0]: coords.insert(0,start_xy); distance += haversine_m(origin,(coords[1][1],coords[1][0]))
    if coords and stop_xy != coords[-1]: distance += haversine_m((coords[-1][1],coords[-1][0]),(stop_xy[1],stop_xy[0])); coords.append(stop_xy)
    geometry = mapping(LineString(coords)) if len(coords)>1 else {"type":"Point","coordinates":coords[0]}
    return {"geometry":geometry,"distance_m":round(distance,1),"duration_seconds":round(distance/WALKING_SPEED_MPS),"walking_speed_mps_assumed":WALKING_SPEED_MPS,"algorithm":algorithm.value,"profile":profile.value,"computation_time_ms":round((perf_counter()-started)*1000,2),"graph_nodes_traversed":len(nodes),"mapped_stair_segments":stair_count,"accessibility_warning":ACCESSIBILITY_WARNING}
