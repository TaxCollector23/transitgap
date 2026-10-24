"""Small geospatial helpers shared by graph construction and routing."""
from __future__ import annotations

from heapq import nsmallest
from math import asin, cos, isfinite, radians, sin, sqrt
from typing import Any, Iterable

import networkx as nx
import numpy as np
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")

EARTH_RADIUS_M = 6_371_000.0


def distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between latitude/longitude pairs."""
    lat1, lon1 = map(radians, a)
    lat2, lon2 = map(radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(min(1.0, max(0.0, h))))


def _unit_sphere(latitude: float, longitude: float) -> tuple[float, float, float]:
    lat, lon = radians(latitude), radians(longitude)
    return cos(lat) * cos(lon), cos(lat) * sin(lon), sin(lat)


def nearest_graph_nodes(graph: nx.Graph, latitude: float, longitude: float,
                        count: int = 1,
                        nodes: Iterable[Any] | None = None) -> list[tuple[Any, float]]:
    """Find the nearest graph nodes, using a cached spherical KD-tree when available.

    Chord distance in unit-sphere coordinates is monotonic with great-circle
    distance, so the KD-tree order is also the geodesic nearest-node order.
    The packaged PyKDTree index avoids scanning the full county for every stop.
    A geodesic scan remains available for small installations without the index.
    """
    count = max(1, int(count))
    if nodes is None:
        index = getattr(graph, "_transitgap_node_index", None)
        if index is None:
            valid_nodes, points = [], []
            for node, attrs in graph.nodes(data=True):
                try:
                    lat, lon = float(attrs["y"]), float(attrs["x"])
                except (KeyError, TypeError, ValueError):
                    continue
                if not isfinite(lat) or not isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
                    continue
                valid_nodes.append(node)
                points.append(_unit_sphere(lat, lon))
            if not valid_nodes:
                raise ValueError("The walking graph has no nodes with valid geographic coordinates")
            try:
                from pykdtree.kdtree import KDTree

                index = (valid_nodes, KDTree(np.asarray(points, dtype=np.float64)))
            except ImportError:
                index = (valid_nodes, None)
            graph._transitgap_node_index = index
        valid_nodes, tree = index
        if tree is not None:
            k = min(count, len(valid_nodes))
            _, positions = tree.query(
                np.asarray([_unit_sphere(latitude, longitude)], dtype=np.float64), k=k
            )
            return [
                (node, distance_m((latitude, longitude),
                                  (float(graph.nodes[node]["y"]), float(graph.nodes[node]["x"]))))
                for node in (valid_nodes[int(position)] for position in np.asarray(positions).reshape(-1))
            ]
        candidates = valid_nodes
    else:
        candidates = list(nodes)
    if not candidates:
        raise ValueError("No walking graph nodes are available for nearest-node selection")
    return nsmallest(
        count,
        ((node, distance_m((latitude, longitude),
                           (float(graph.nodes[node]["y"]), float(graph.nodes[node]["x"]))))
         for node in candidates),
        key=lambda item: item[1],
    )


def nearest_graph_node(graph: nx.Graph, latitude: float, longitude: float,
                       nodes: Iterable[Any] | None = None) -> tuple[Any, float]:
    """Find the true nearest graph node."""
    return nearest_graph_nodes(graph, latitude, longitude, count=1, nodes=nodes)[0]
