import networkx as nx
import pytest
from backend.app.gaps import GapIndex, walkshed
from backend.app.models import Profile


def graph():
    g = nx.MultiDiGraph()
    for n in range(4):
        g.add_node(n, x=-121.9 + n * 0.001, y=37.33)
    for u, v in ((0, 1), (1, 2), (2, 3)):
        for a, b in ((u, v), (v, u)):
            g.add_edge(a, b, length=100, highway="steps" if u == 1 else "footway")
    return g


def test_reverse_walkshed_excludes_steps_and_counts_reciprocals_once():
    g = graph()
    standard = walkshed(g, 3, Profile.standard)
    wheelchair = walkshed(g, 3, Profile.wheelchair)
    assert standard["reachable_length_m"] == 300
    assert wheelchair["reachable_length_m"] == 100
    assert standard["walkshed_polygon"] is not None
    assert standard["documented_length_share"] == 0


def test_cutoff_accounts_for_partial_edges_and_direction():
    g = nx.MultiDiGraph()
    g.add_node(1, x=-121.9, y=37.33)
    g.add_node(2, x=-121.89, y=37.33)
    g.add_edge(1, 2, length=1000)
    assert walkshed(g, 2, Profile.standard)["reachable_length_m"] == 720
    assert walkshed(g, 1, Profile.standard)["reachable_length_m"] == 0


def test_gap_cache_roundtrip_and_zero_denominator(tmp_path):
    g = graph()
    stops = [
        {
            "stop_id": "s",
            "stop_name": "Fixture",
            "graph_node": 3,
            "latitude": 37.33,
            "longitude": -121.897,
            "wheelchair_boarding": 0,
        }
    ]
    index = GapIndex(g, stops, tmp_path)
    index.prepare(1)
    detail = index.detail("s")
    assert detail["gap_score"] == pytest.approx(0.6667, abs=0.0001)
    assert detail["wheelchair_boarding"] == 0
    assert GapIndex(g, stops, tmp_path).summary()["evaluated_stop_count"] == 1
    # Ad-hoc queries must not silently change the prepared comparison sample.
    index.stops['other'] = {**stops[0], 'stop_id': 'other'}
    index.detail('other')
    assert len(index.cache) == 2
    assert index.summary()['evaluated_stop_count'] == 1
    g.remove_edges_from(list(g.edges(keys=True)))
    blank = GapIndex(g, stops, tmp_path).detail("s")
    assert blank["gap_score"] is None
