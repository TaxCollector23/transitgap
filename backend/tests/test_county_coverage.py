from __future__ import annotations

import zipfile

import networkx as nx
from shapely.geometry import Point

from backend.app import data_loader
from backend.app import main


def test_packaged_boundary_is_the_santa_clara_county_polygon():
    boundary = data_loader.load_county_boundary()
    assert boundary.geom_type == "Polygon"
    assert boundary.is_valid
    assert boundary.covers(Point(-121.903, 37.3296))  # Diridon Station
    assert not boundary.covers(Point(-122.4, 37.8))


def test_county_stop_filter_rejects_stops_outside_the_county(tmp_path, monkeypatch):
    feed = tmp_path / "gtfs_vta.zip"
    with zipfile.ZipFile(feed, "w") as archive:
        archive.writestr("stops.txt", "stop_id,stop_name,stop_lat,stop_lon\n"
                         "inside,Diridon,37.3296,-121.903\n"
                         "outside,Outside county,37.8,-122.4\n")
    graph = nx.MultiDiGraph()
    graph.add_node("walk", y=37.3296, x=-121.903)
    monkeypatch.setattr(data_loader, "_nearest_graph_node", lambda *_args: "walk")
    stops = data_loader.load_stops(graph, data_loader.COUNTY_RADIUS_M,
                                   directory=tmp_path, region=data_loader.COUNTY_REGION)
    assert [stop["stop_id"] for stop in stops] == ["inside"]


def test_api_origin_validation_uses_the_county_boundary(monkeypatch):
    monkeypatch.setitem(main.state, "region", data_loader.COUNTY_REGION)
    assert main._inside(37.3296, -121.903)
    assert not main._inside(37.8, -122.4)


def test_coverage_response_includes_county_boundary_and_source_limit(monkeypatch):
    monkeypatch.setitem(main.state, "region", data_loader.COUNTY_REGION)
    monkeypatch.setitem(main.state, "radius_m", data_loader.COUNTY_RADIUS_M)
    coverage = main.coverage()
    assert coverage["region"] == "Santa Clara County"
    assert coverage["boundary"]["type"] == "Polygon"
    assert "City of San Jose" in coverage["description"]
