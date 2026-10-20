"""AI-assisted inspection sensitivity; historical module name, not student credit.

A score counts distinct sampled origin/stop pairs that change within the time
budget when the candidate connection is blocked. Other unknowns stay passable.
"""
from __future__ import annotations

from math import isfinite
from typing import Any, Sequence
import networkx as nx

ASSUMPTIONS = (
    "Directed travel toward each stop; walk_seconds includes the selected profile cost. "
    "Other unknown connections remain usable in both hypothetical scenarios. "
    "Counts describe sampled graph journeys, not people, ridership, safety or official priority."
)


def _equivalent_edges(graph, edge):
    """Identical same-direction records are duplicates; distinct attributes remain alternatives."""
    u, v, key = edge
    attrs = graph[u][v][key]
    return {(u, v, other) for other, data in graph[u][v].items() if data == attrs}


def rank_inspection_candidates(graph: nx.MultiDiGraph, *, stop_nodes: dict[str, Any],
                               origin_nodes: Sequence[Any], candidates: Sequence[dict[str, Any]],
                               time_budget_seconds: float) -> list[dict[str, Any]]:
    try:
        budget = float(time_budget_seconds)
    except (ValueError, TypeError) as exc:
        raise ValueError("Travel budget must be finite and positive") from exc
    if not isfinite(budget) or budget <= 0:
        raise ValueError("Travel budget must be finite and positive")
    if not graph.is_directed() or not graph.is_multigraph():
        raise ValueError("A directed MultiDiGraph is required")
    origins = sorted(set(origin_nodes), key=lambda x: (type(x).__name__, str(x)))
    stops = sorted(stop_nodes.items())
    if not candidates or not origins or not stops:
        return []
    for _, _, _, data in graph.edges(keys=True, data=True):
        try:
            cost = float(data["walk_seconds"])
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("Every graph edge needs a finite nonnegative walk_seconds cost") from exc
        if not isfinite(cost) or cost < 0:
            raise ValueError("Every graph edge needs a finite nonnegative walk_seconds cost")
    sample_count = len(origins) * len(stops)
    complete = all(n in graph for n in origins) and all(n in graph for _, n in stops)

    def outcomes(network):
        pairs = set()
        reverse = network.reverse(copy=False)
        for stop_id, node in stops:
            reach = nx.single_source_dijkstra_path_length(reverse, node, cutoff=budget, weight=lambda u, v, data: min(float(d["walk_seconds"]) for d in data.values()))
            pairs.update((origin, stop_id) for origin in origins if origin in reach)
        return pairs

    baseline = outcomes(graph) if complete else set()
    records, seen = [], {}
    for candidate in sorted(candidates, key=lambda c: str(c.get("candidate_id", ""))):
        identity = str(candidate.get("candidate_id", ""))
        if not identity:
            raise ValueError("Candidate ID is required")
        raw_edges = candidate.get("edges") or [candidate.get("edge")]
        try:
            edges = {tuple(edge) for edge in raw_edges if edge is not None}
        except TypeError as exc:
            raise ValueError("Candidate edges must be (u, v, key) triples") from exc
        if any(len(edge) != 3 for edge in edges):
            raise ValueError("Candidate edges must be (u, v, key) triples")
        signature = frozenset(edges)
        if identity in seen:
            if seen[identity] != signature:
                raise ValueError("One candidate ID refers to conflicting connections")
            continue
        seen[identity] = signature
        available = complete and bool(edges) and all(graph.has_edge(*edge) for edge in edges)
        result = {"candidate_id": identity, "source_url": candidate.get("source_url"),
                  "score": None, "affected_pairs": [], "sample_count": sample_count,
                  "assumptions": ASSUMPTIONS, "status": "UNAVAILABLE"}
        if available:
            blocked = set().union(*(_equivalent_edges(graph, edge) for edge in edges))
            # Equivalent records under different IDs share one result and retain aliases.
            duplicate = next((r for signature_, r in records if signature_ == blocked), None)
            if duplicate is not None:
                duplicate.setdefault("equivalent_candidate_ids", []).append(identity)
                continue
            network = nx.subgraph_view(graph, filter_edge=lambda u, v, k: (u, v, k) not in blocked)
            changed = baseline.symmetric_difference(outcomes(network))
            result.update(score=len(changed), affected_pairs=[list(pair) for pair in sorted(changed, key=lambda p: (type(p[0]).__name__, str(p[0]), p[1]))], status="MODELED")
            records.append((blocked, result))
        else:
            records.append((None, result))
    return sorted((record for _, record in records), key=lambda r: (r["score"] is None, -(r["score"] or 0), r["candidate_id"]))
