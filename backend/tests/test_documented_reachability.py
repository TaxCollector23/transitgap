import networkx as nx
import pytest
from zipfile import ZipFile

from backend.app.models import Profile
from backend.app.reachability import ReachabilityIndex, critical_unknowns, pilot_gtfs_stops


def edge(surface="concrete", width="1.2"):
    return {"length": 100, "geometry": [[-121.903, 37.3296], [-121.902, 37.3296]],
            "highway": "footway", "osmid": 12345, "surface": surface, "width": width}


def index_for(graph, stops):
    metadata = {"source": "OpenStreetMap via OSMnx", "graph_modified_at": "2026-10-20T00:00:00Z"}
    return ReachabilityIndex(graph, stops, metadata, [{"feed_version": "fixture-vta"}])


def test_documented_reach_is_subset_of_possible_and_unknown_edges_are_explained():
    graph = nx.MultiDiGraph()
    for node in range(4):
        graph.add_node(node, x=-121.902 if node == 3 else -121.903, y=37.3296)
    graph.add_edge(0, 3, key=0, **edge())
    graph.add_edge(1, 3, key=0, **edge(width=None))
    graph.add_edge(2, 3, key=0, length=100, highway="steps", osmid=99,
                   geometry=[[-121.903, 37.3296], [-121.902, 37.3296]])
    stop = {"stop_id": "real-vta-fixture", "stop_name": "Fixture stop", "latitude": 37.3296,
            "longitude": -121.902, "graph_node": "3", "connector_distance_m": 5,
            "wheelchair_boarding": 0}
    result = index_for(graph, [stop]).analyze(stop["stop_id"], Profile.wheelchair, 10, 20)

    assert result["status"] == "OK"
    assert result["documented"]["reachable_sample_origins"] == 1  # node 0; the stop is not an origin
    assert result["possible"]["reachable_sample_origins"] == 2
    assert result["unknown_gap"]["sample_origin_count"] == 1
    assert result["unknown_gap"]["critical_unknown_edge_count"] == 1
    assert result["unknown_gap"]["examples"][0]["osm_way_id"] == "12345"
    assert result["unknown_gap"]["examples"][0]["evidence_status"] == "UNKNOWN"
    assert result["documented"]["reachable_sample_origins"] <= result["possible"]["reachable_sample_origins"]


def test_toward_stop_direction_is_not_reversed():
    graph = nx.MultiDiGraph()
    graph.add_node(0, x=-121.903, y=37.3296)
    graph.add_node(1, x=-121.902, y=37.3296)
    graph.add_edge(0, 1, key=0, **edge())
    stop = {"stop_id": "s", "stop_name": "Stop", "latitude": 37.3296,
            "longitude": -121.903, "graph_node": "0", "connector_distance_m": 5}
    result = index_for(graph, [stop]).analyze("s", Profile.wheelchair, 10, 20)
    assert result["possible"]["reachable_sample_origins"] == 0


def test_stop_connection_over_limit_is_not_silently_snapped():
    graph = nx.MultiDiGraph()
    graph.add_node(1, x=-121.903, y=37.3296)
    stop = {"stop_id": "s", "stop_name": "Stop", "latitude": 37.3296,
            "longitude": -121.903, "graph_node": "1", "connector_distance_m": 40}
    result = index_for(graph, [stop]).analyze("s", Profile.wheelchair, 10, 20)
    assert result["status"] == "STOP_CONNECTION_UNKNOWN"
    assert "does not infer a path" in result["message"]


def test_pilot_stop_loader_keeps_real_feed_stops_with_long_nearest_node_gaps(tmp_path):
    archive = tmp_path / "gtfs.zip"
    with ZipFile(archive, "w") as output:
        output.writestr("stops.txt", "stop_id,stop_name,stop_lat,stop_lon,wheelchair_boarding\ns,Actual VTA stop,37.3296,-121.900,0\n")
    graph = nx.MultiDiGraph()
    graph.add_node(1, x=-121.903, y=37.3296)
    stops = pilot_gtfs_stops(graph, archive)
    assert len(stops) == 1
    assert stops[0]["stop_id"] == "s"
    assert stops[0]["connector_distance_m"] > 35
    index = index_for(graph, stops)
    assert index.analyze("s")["status"] == "STOP_CONNECTION_UNKNOWN"


@pytest.mark.parametrize("profile,edge_data,expected", [
    (Profile.standard, {"highway": "footway"}, ()),
    (Profile.wheelchair, {"highway": "footway"}, ("surface", "width")),
    (Profile.wheelchair, {"highway": "footway", "surface": "concrete", "width": "1m"}, ()),
    (Profile.low_vision, {"highway": "footway"}, ("lighting",)),
])
def test_only_relevant_missing_predicates_enter_documented_scenario(profile, edge_data, expected):
    graph_node = {"x": -121.903, "y": 37.3296}
    assert critical_unknowns(edge_data, graph_node, graph_node, profile) == expected


def test_invalid_study_bounds_are_rejected():
    graph = nx.MultiDiGraph()
    graph.add_node(1, x=-121.903, y=37.3296)
    stop = {"stop_id": "s", "stop_name": "Stop", "latitude": 37.3296,
            "longitude": -121.903, "graph_node": "1", "connector_distance_m": 2}
    index = index_for(graph, [stop])
    with pytest.raises(ValueError, match="Time budget"):
        index.analyze("s", Profile.wheelchair, 16, 20)


def test_toward_stop_partial_geometry_is_adjacent_to_destination_and_difference_is_retained():
    from backend.app.reachability import _feature
    graph = nx.MultiDiGraph()
    graph.add_node(0, x=-121.903, y=37.3296)
    graph.add_node(1, x=-121.902, y=37.3296)
    data = edge()
    partial = _feature(graph, 0, 1, 0, data, .25)
    coords = partial['geometry']['coordinates']
    assert coords[0][0] == pytest.approx(-121.90225)
    assert coords[-1][0] == pytest.approx(-121.902)
    difference = _feature(graph, 0, 1, 0, data, .5, .1)
    assert difference['geometry']['coordinates'][0][0] == pytest.approx(-121.9025)
    assert difference['geometry']['coordinates'][-1][0] == pytest.approx(-121.9021)


def test_width_sensitivity_does_not_remove_known_barriers_or_surface_requirement():
    attrs = {'highway': 'footway', 'surface': 'concrete'}
    assert critical_unknowns(attrs, {}, {}, Profile.wheelchair) == ('width',)
    assert critical_unknowns(attrs, {}, {}, Profile.wheelchair, 'width_optional_sensitivity') == ()
    assert critical_unknowns({'highway':'footway'}, {}, {}, Profile.wheelchair, 'width_optional_sensitivity') == ('surface',)


def test_missing_stop_connector_distance_remains_unknown():
    graph=nx.MultiDiGraph();graph.add_node('s',x=-121.903,y=37.3296)
    stop={'stop_id':'s','stop_name':'Synthetic stop','latitude':37.3296,'longitude':-121.903,
          'graph_node':'s','connector_distance_m':None}
    result=index_for(graph,[stop]).analyze('s')
    assert result['status']=='STOP_CONNECTION_UNKNOWN'
    assert result['stop']['connector_distance_m'] is None
    assert 'No usable mapped-node connection' in result['message']
