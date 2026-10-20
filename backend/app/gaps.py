"""Ten-minute reverse network walksheds; bounded, reproducible pilot analysis.

Reachable length counts each physical directed pair once, with fractional edge
length at the cutoff. Travel follows the graph toward the stop (reverse search).
Buffered lines are visual envelopes, never land area or population estimates.
"""

from __future__ import annotations
import json
from functools import lru_cache
from pathlib import Path
import networkx as nx
from shapely.geometry import LineString, mapping
from shapely.ops import unary_union, substring
from .models import Profile
from .routing import _weight, _edge_coords, _length_m
from .profiles import evaluate, SPEED_MPS

VERSION = "network-gap-v3"
WARNING = "Modelled 10-minute network reach, not verified accessibility. Different assumed speeds and mapped constraints both affect the gap. Unknown map attributes remain unknown. Buffered paths are visual envelopes only."


def walkshed(graph, node, profile, minutes=10):
    cutoff = minutes * 60 * SPEED_MPS[profile.value]
    reverse = graph.reverse(copy=False)
    distances = nx.single_source_dijkstra_path_length(
        reverse,
        node,
        cutoff=cutoff,
        weight=lambda v, u, data: _weight(graph, u, v, data, profile, {}),
    )
    portions = {}
    for end, spent in distances.items():
        for start, _, key, attrs in graph.in_edges(end, keys=True, data=True):
            weight = _weight(graph, start, end, {key: attrs}, profile, {})
            if weight is None or weight <= 0:
                continue
            fraction = min(1.0, max(0.0, (cutoff - spent) / weight))
            if not fraction:
                continue
            length = _length_m(graph, start, end, attrs)
            coords = _edge_coords(graph, start, end, attrs)
            # Reciprocal geometry represents the same physical street segment.
            canonical = tuple(map(tuple, coords))
            canonical = min(canonical, canonical[::-1])
            identity = (canonical, str(attrs.get("osmid", "")))
            known = evaluate(attrs, graph.nodes[start], graph.nodes[end], profile)[4]
            same_direction = tuple(map(tuple, coords)) == canonical
            interval = (1 - fraction, 1.0) if same_direction else (0.0, fraction)
            item = portions.setdefault(
                identity,
                {
                    "length": length,
                    "known": bool(known),
                    "line": LineString(canonical),
                    "intervals": [],
                },
            )
            item["intervals"].append(interval)
    length = documented = 0.0
    lines = []
    for item in portions.values():
        merged = []
        for left, right in sorted(item["intervals"]):
            if merged and left <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], right)
            else:
                merged.append([left, right])
        fraction = sum(right - left for left, right in merged)
        length += fraction * item["length"]
        if item["known"]:
            documented += fraction * item["length"]
        for left, right in merged:
            line = substring(item["line"], left, right, normalized=True)
            if line.geom_type == "LineString":
                lines.append(mapping(line))
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform

    to_m = Transformer.from_crs(4326, 26910, always_xy=True).transform
    to_wgs = Transformer.from_crs(26910, 4326, always_xy=True).transform
    envelope = (
        transform(
            to_wgs,
            unary_union([transform(to_m, shape(line)).buffer(5) for line in lines]),
        )
        if lines
        else None
    )
    return {
        "walkshed_polygon": mapping(envelope) if envelope is not None else None,
        "polygon_method": "5 metre buffered reachable network, for display only; gap uses network length",
        "reachable_length_m": round(length, 1),
        "documented_length_share": round(documented / length, 4) if length else None,
        "geometry": {"type": "GeometryCollection", "geometries": lines},
        "reachable_nodes": len(distances),
    }


class GapIndex:
    def __init__(self, graph, stops, directory: Path):
        self.graph, self.stops, self.directory = (
            graph,
            {s["stop_id"]: s for s in stops},
            directory,
        )
        self.cache = {}
        self.prepared_ids = set()
        from hashlib import sha256
        from .data_loader import (
            graph_cache_path,
            COUNTY_REGION,
            COUNTY_RADIUS_M,
            DEFAULT_RADIUS_M,
        )

        region = COUNTY_REGION if graph.number_of_nodes() > 100_000 else "diridon"
        graph_path = graph_cache_path(
            directory,
            COUNTY_RADIUS_M if region == COUNTY_REGION else DEFAULT_RADIUS_M,
            region,
        )
        digest = (
            sha256(graph_path.read_bytes()).hexdigest() if graph_path.exists() else None
        )
        self.signature = [
            VERSION,
            sha256((Path(__file__).parent / "profiles.py").read_bytes()).hexdigest(),
            digest,
            graph.number_of_nodes(),
            graph.number_of_edges(),
            sorted(self.stops),
        ]
        self.path = directory / "stop-gaps-v2.json"
        if self.path.exists():
            try:
                cached = json.loads(self.path.read_text())
                if cached["signature"] == self.signature:
                    self.cache = cached["stops"]
                    self.prepared_ids = set(cached.get("prepared_ids", self.cache))
            except (OSError, ValueError, KeyError):
                pass

    def detail(self, stop_id):
        if stop_id not in self.stops:
            raise KeyError(stop_id)
        if stop_id not in self.cache:
            stop = self.stops[stop_id]
            node = stop["graph_node"]
            if node not in self.graph and str(node).isdigit():
                node = int(node)
            standard = walkshed(self.graph, node, Profile.standard)
            wheelchair = walkshed(self.graph, node, Profile.wheelchair)
            base = standard["reachable_length_m"]
            gap = (
                max(0.0, 1 - wheelchair["reachable_length_m"] / base)
                if base > 0
                else None
            )
            self.cache[stop_id] = {
                "stop_id": stop_id,
                "stop_name": stop["stop_name"],
                "latitude": stop["latitude"],
                "longitude": stop["longitude"],
                "gap_score": round(gap, 4) if gap is not None else None,
                "standard": standard,
                "wheelchair": wheelchair,
                "wheelchair_boarding": stop.get("wheelchair_boarding", 0),
                "duration_minutes": 10,
                "speeds_mps": {"standard": 1.2, "wheelchair": 0.9},
                "warning": WARNING,
                "metric": "unique mapped pedestrian network length reachable toward stop, including fractional edges",
                "boundary_status": "Study is clipped to the county graph; routes near its boundary may be truncated.",
            }
        if len(self.cache) > 100:
            oldest = next(
                (
                    key
                    for key in self.cache
                    if key not in self.prepared_ids and key != stop_id
                ),
                None,
            )
            if oldest is not None:
                self.cache.pop(oldest)
        return self.cache[stop_id]

    def prepare(self, limit=32):
        # Spatially distributed sample of real stops, not a countywide ranking.
        selected = sorted(
            self.stops.values(),
            key=lambda s: (s["latitude"], s["longitude"], s["stop_id"]),
        )
        stride = max(1, len(selected) // limit)
        self.prepared_ids = {stop["stop_id"] for stop in selected[::stride][:limit]}
        for stop in selected[::stride][:limit]:
            self.detail(stop["stop_id"])
        try:
            temp = self.path.with_suffix(".part")
            temp.write_text(
                json.dumps(
                    {
                        "signature": self.signature,
                        "stops": self.cache,
                        "prepared_ids": sorted(self.prepared_ids),
                    },
                    separators=(",", ":"),
                )
            )
            temp.replace(self.path)
        except OSError:
            pass

    def summary(self, limit=10):
        ranked = sorted(
            (
                r
                for key, r in self.cache.items()
                if key in self.prepared_ids and r["gap_score"] is not None
            ),
            key=lambda r: (-r["gap_score"], r["stop_id"]),
        )
        features = []
        for item in ranked[:limit]:
            properties = {
                k: v for k, v in item.items() if k not in {"standard", "wheelchair"}
            }
            properties["standard_length_m"] = item["standard"]["reachable_length_m"]
            properties["wheelchair_length_m"] = item["wheelchair"]["reachable_length_m"]
            properties["documented_length_share"] = item["wheelchair"][
                "documented_length_share"
            ]
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [item["longitude"], item["latitude"]],
                    },
                    "properties": properties,
                }
            )
        return {
            "type": "FeatureCollection",
            "features": features,
            "evaluated_stop_count": len(ranked),
            "loaded_stop_count": len(self.stops),
            "scope": "Spatially distributed sample of loaded VTA stops; ranking applies only to evaluated stops.",
            "warning": WARNING,
            "method_version": VERSION,
        }
