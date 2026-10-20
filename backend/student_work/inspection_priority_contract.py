"""AI-assisted contract: physical candidates may group duplicate parallel records.

Run with backend/.venv/bin/python -m pytest backend/student_work/inspection_priority_contract.py.
"""
import networkx as nx
import pytest

from backend.app.research.inspection_priority_student import rank_inspection_candidates


def edge(graph, a, b, seconds=1, key=0):
    graph.add_edge(a, b, key=key, walk_seconds=seconds)


def run(graph, stops, origins, candidates, budget=10):
    return rank_inspection_candidates(
        graph, stop_nodes=stops, origin_nodes=origins, candidates=candidates,
        time_budget_seconds=budget,
    )


def candidate(identifier, edge_tuple):
    return {"candidate_id": identifier, "edge": edge_tuple,
            "source_url": f"https://www.openstreetmap.org/way/{identifier}"}


def by_id(results):
    return {item["candidate_id"]: item for item in results}


def test_bridge_counts_unique_origins_whose_toward_stop_reach_changes():
    graph = nx.MultiDiGraph()
    edge(graph, "a", "bridge"); edge(graph, "b", "bridge"); edge(graph, "bridge", "stop")
    result = by_id(run(graph, {"vta-1": "stop"}, ["a", "b"],
                       [candidate("bridge", ("bridge", "stop", 0))]))["bridge"]
    assert result["score"] == 2
    assert result["sample_count"] == 2
    assert result["source_url"].endswith("/way/bridge")


def test_dead_end_candidate_has_zero_reachability_value():
    graph = nx.MultiDiGraph()
    edge(graph, "origin", "stop"); edge(graph, "origin", "dead")
    result = by_id(run(graph, {"vta-1": "stop"}, ["origin"],
                       [candidate("dead-end", ("origin", "dead", 0))]))["dead-end"]
    assert result["score"] == 0


def test_ties_have_stable_candidate_id_order():
    graph = nx.MultiDiGraph()
    edge(graph, "o1", "s1"); edge(graph, "o2", "s2")
    results = run(graph, {"vta-1": "s1", "vta-2": "s2"}, ["o1", "o2"],
                  [candidate("z", ("o2", "s2", 0)), candidate("a", ("o1", "s1", 0))])
    assert [item["candidate_id"] for item in results] == ["a", "z"]
    assert [item["score"] for item in results] == [1, 1]


def test_direction_is_origin_toward_stop_not_outward_from_stop():
    graph = nx.MultiDiGraph()
    edge(graph, "stop", "origin")
    result = run(graph, {"vta-1": "stop"}, ["origin"],
                 [candidate("outward-only", ("stop", "origin", 0))])
    assert by_id(result)["outward-only"]["score"] == 0


def test_multiple_stops_count_unique_origin_stop_pairs_not_duplicate_edges():
    graph = nx.MultiDiGraph()
    edge(graph, "origin", "shared"); edge(graph, "origin", "shared", key=1)
    edge(graph, "shared", "s1"); edge(graph, "shared", "s2")
    result = by_id(run(graph, {"vta-1": "s1", "vta-2": "s2"}, ["origin"],
                       [candidate("shared", ("origin", "shared", 0))]))["shared"]
    assert result["score"] == 2


@pytest.mark.parametrize("stops,origins,candidates", [
    ({"s": "stop"}, ["o"], []),
    ({"s": "stop"}, [], [candidate("c", ("o", "stop", 0))]),
    ({}, ["o"], [candidate("c", ("o", "stop", 0))]),
])
def test_empty_candidates_zero_samples_or_missing_stop_data_return_no_false_priority(stops, origins, candidates):
    assert run(nx.MultiDiGraph(), stops, origins, candidates) == []


def test_unavailable_candidate_edge_is_preserved_as_null_not_zero():
    graph = nx.MultiDiGraph()
    result = run(graph, {"s": "stop"}, ["origin"],
                 [candidate("missing", ("origin", "stop", 0))])
    assert by_id(result)["missing"]["score"] is None


def test_fixed_input_is_deterministic_and_reports_assumptions():
    graph = nx.MultiDiGraph(); edge(graph, "origin", "stop")
    candidates = [candidate("c", ("origin", "stop", 0))]
    first = run(graph, {"s": "stop"}, ["origin"], candidates)
    second = run(graph, {"s": "stop"}, ["origin"], candidates)
    assert first == second
    assert first[0]["assumptions"]


def test_small_graph_result_matches_exhaustive_reference_for_unique_pairs():
    graph = nx.MultiDiGraph()
    edge(graph, "o1", "u"); edge(graph, "u", "s1")
    edge(graph, "o2", "u"); edge(graph, "u", "s2")
    result = by_id(run(graph, {"vta-1": "s1", "vta-2": "s2"}, ["o1", "o2"],
                       [candidate("u", ("u", "s1", 0))]))["u"]
    # Both origins reach s1 through u -> s1; blocking it changes both pairs.
    assert result["score"] == 2
    assert result["affected_pairs"] == [["o1", "vta-1"], ["o2", "vta-1"]]


def test_results_include_sample_count_and_stable_candidate_ids():
    graph = nx.MultiDiGraph(); edge(graph, "o", "s")
    result = run(graph, {"stop-1": "s"}, ["o"],
                 [candidate("id-1", ("o", "s", 0))])
    assert result[0]["candidate_id"] == "id-1"
    assert result[0]["sample_count"] == 1
