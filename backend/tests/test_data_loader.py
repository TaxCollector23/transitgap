from __future__ import annotations

import zipfile

import networkx as nx
import pytest

from backend.app import data_loader


def test_compact_graph_preserves_routing_data(tmp_path):
    from shapely.geometry import LineString
    from backend.app.models import Algorithm, Profile
    from backend.app.routing import calculate_route

    graph = nx.MultiDiGraph(crs="epsg:4326")
    graph.add_node(1, x=-121.903, y=37.3296, highway="crossing")
    graph.add_node(2, x=-121.903, y=37.3297)
    graph.add_edge(1, 2, key=7, highway="footway", length=12,
                   geometry=LineString([(-121.903, 37.3296), (-121.903, 37.3297)]))
    path = tmp_path / "graph.jsonl.gz"
    data_loader.write_compact_graph(graph, path)
    loaded = data_loader.read_compact_graph(path)
    assert set(loaded.nodes) == {1, 2}
    assert loaded.nodes[1]["highway"] == "crossing"
    assert loaded[1][2][7]["highway"] == "footway"
    result = calculate_route(loaded, (37.3296, -121.903), 2, Algorithm.dijkstra,
                             Profile.standard, {"stop_id": "fixture", "stop_name": "Fixture stop", "latitude": 37.3297,
                                                "longitude": -121.903})
    assert result["distance_m"] == 12
    assert result["geometry"]["coordinates"][-1] == (-121.903, 37.3297)


def test_cached_graph_load_is_reused_and_manifest_write_can_be_read_only(tmp_path, monkeypatch):
    path = tmp_path / "walk-network-1500m.graphml"
    path.write_text("cached graph marker", encoding="utf-8")
    graph = nx.MultiDiGraph()
    graph.add_node(1, y=37.3296, x=-121.903)
    loads = []
    monkeypatch.setattr(data_loader.ox, "load_graphml", lambda _path: (loads.append(_path) or graph))
    monkeypatch.setattr(data_loader.ox, "graph_from_point", lambda **_kwargs: pytest.fail("cache miss triggered an external OSM request"))
    monkeypatch.setattr(data_loader, "_write_metadata", lambda *_args: (_ for _ in ()).throw(PermissionError("read only")))
    data_loader._GRAPH_CACHE.clear()

    first = data_loader.load_graph(directory=tmp_path)
    second = data_loader.load_graph(directory=tmp_path)
    assert first is graph and second is graph
    assert len(loads) == 1


def test_stops_still_load_when_bundled_cache_is_read_only(tmp_path, monkeypatch):
    graph_path = tmp_path / "walk-network-1500m.graphml"
    graph_path.write_text("fixture graph", encoding="utf-8")
    feed = tmp_path / "gtfs_vta.zip"
    with zipfile.ZipFile(feed, "w") as archive:
        archive.writestr("stops.txt", "stop_id,stop_name,stop_lat,stop_lon\nfixture,Test Stop,37.3296,-121.9030\n")
    graph = nx.MultiDiGraph()
    graph.add_node(123, y=37.3296, x=-121.903)
    original_write_text = type(graph_path).write_text

    def read_only_write(path, *args, **kwargs):
        if path.name.startswith("stops-v"):
            raise PermissionError("read only package directory")
        return original_write_text(path, *args, **kwargs)

    monkeypatch.setattr(type(graph_path), "write_text", read_only_write)
    stops = data_loader.load_stops(graph, directory=tmp_path)
    assert len(stops) == 1
    assert stops[0]["stop_id"] == "fixture"
    assert stops[0]["graph_node"] == "123"
