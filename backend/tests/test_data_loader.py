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


def test_serverless_graph_never_rescans_build_manifest(tmp_path,monkeypatch):
    graph=nx.MultiDiGraph();graph.add_node(1,x=-121.9,y=37.3)
    path=tmp_path/'walk-network-1500m.jsonl.gz'
    data_loader.write_compact_graph(graph,path)
    monkeypatch.setenv('VERCEL','1')
    monkeypatch.delenv('TRANSITGAP_PREPARING_DATA',raising=False)
    monkeypatch.setattr(data_loader,'_write_metadata',lambda *_:pytest.fail('runtime manifest regeneration'))
    assert len(data_loader.load_graph(directory=tmp_path))==1


def test_file_signature_tracks_content_instead_of_packaging_mtime(tmp_path):
    import os
    path=tmp_path/'source.zip';path.write_bytes(b'original')
    first=data_loader.file_signature(path)
    os.utime(path,(100,100))
    assert data_loader.file_signature(path)==first
    path.write_bytes(b'changed!')
    assert data_loader.file_signature(path)!=first


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


def test_compact_graph_certifies_admissible_geographic_scale(tmp_path):
    import networkx as nx
    from backend.app.routing import _heuristic, _run
    from backend.app.models import Algorithm, Profile
    graph=nx.MultiDiGraph()
    for node,x in [('o',0),('x',1),('s',.001)]:graph.add_node(node,x=x,y=0)
    graph.add_edge('o','s',length=10)
    graph.add_edge('o','x',length=1)
    graph.add_edge('x','s',length=1)
    path=tmp_path/'short-lengths.jsonl.gz'
    data_loader.write_compact_graph(graph,path)
    loaded=data_loader.read_compact_graph(path)
    assert 0 < loaded.graph['transitgap_heuristic_scale'] < 1
    assert _heuristic(loaded,'x','s')<=1
    assert _run(loaded,'o','s',Algorithm.astar,Profile.standard)[1]==2


def test_vta_destinations_are_boarding_stops_linked_to_their_station(tmp_path):
    feed = tmp_path / "gtfs_vta.zip"
    with zipfile.ZipFile(feed, "w") as archive:
        archive.writestr(
            "stops.txt",
            "stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station,wheelchair_boarding\n"
            "PS_TEST,Test Station,37.3296,-121.9030,1,,1\n"
            "5374,Test Station,37.3296,-121.9030,0,PS_TEST,0\n"
            "E1,Test Station Entrance,37.3297,-121.9030,2,PS_TEST,1\n"
            "N1,Generic node,37.3296,-121.9030,3,PS_TEST,\n"
            "100,Plain Bus Stop,37.3296,-121.9030,0,,2\n",
        )
    graph = nx.MultiDiGraph()
    graph.add_node(1, y=37.3296, x=-121.903)
    stops = data_loader.load_stops(graph, directory=tmp_path)
    assert [s["stop_id"] for s in stops] == ["5374", "100"]
    platform, bus = stops
    assert platform["station_id"] == "PS_TEST" and platform["station_name"] == "Test Station"
    assert platform["wheelchair_boarding"] == 1  # inherited from the parent station
    assert [e["name"] for e in platform["entrances"]] == ["Test Station Entrance"]
    assert bus["station_id"] is None and bus["wheelchair_boarding"] == 2
    assert {s["agency"] for s in stops} == {"vta"}
    # The cached stop list must keep the same answer.
    assert [s["stop_id"] for s in data_loader.load_stops(graph, directory=tmp_path)] == ["5374", "100"]
