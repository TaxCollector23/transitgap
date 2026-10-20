import networkx as nx
from backend.app.groundtruth_cache import load_groundtruth


def test_plain_snapshot_roundtrip_and_source_invalidation(tmp_path, monkeypatch):
    from backend.app import groundtruth_cache
    graph = nx.MultiDiGraph()
    graph.add_node(1, x=-121.903, y=37.3296)
    graph.add_node(2, x=-121.903, y=37.3297)
    graph.add_edge(1, 2, length=12, highway='footway', osmid=1)
    stops = [{'stop_id':'s', 'stop_name':'Fixture', 'graph_node':2, 'latitude':37.3297, 'longitude':-121.903}]
    city = {'features':[], 'metadata':{'availability':'unavailable'}}
    built = load_groundtruth(graph, stops, city, tmp_path, ['fixture', 1])
    assert (tmp_path / 'evidence-index-v1.json.gz').exists()
    original = groundtruth_cache.GroundTruthIndex.__init__
    def no_recompute(*args, **kwargs):
        raise AssertionError('Recomputed a valid evidence snapshot')
    monkeypatch.setattr(groundtruth_cache.GroundTruthIndex, '__init__', no_recompute)
    loaded = load_groundtruth(graph, stops, city, tmp_path, ['fixture', 1])
    assert loaded.evaluation() == built.evaluation()
    assert loaded.get_priorities() == built.get_priorities()
    monkeypatch.setattr(groundtruth_cache.GroundTruthIndex, '__init__', original)
    changed = load_groundtruth(graph, stops, city, tmp_path, ['fixture', 2])
    assert changed.evaluation() == built.evaluation()
