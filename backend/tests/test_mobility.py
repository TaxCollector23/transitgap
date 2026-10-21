from time import perf_counter
import networkx as nx
import pytest
from backend.app.models import Algorithm, Profile
from backend.app.profiles import evaluate, incline_percent
from backend.app.routing import calculate_route, _run
from backend.app.geospatial import nearest_graph_node


def test_mapped_barriers_excluded_for_mobility_profiles():
    for profile in (Profile.wheelchair, Profile.avoid_mapped_stairs, Profile.stroller):
        for edge in ({"highway": "steps"}, {"barrier": "stile"}):
            assert not evaluate(edge, {}, {}, profile)[0]
        assert evaluate({"wheelchair": "no"}, {}, {}, profile)[0] == (profile == Profile.stroller)
        assert evaluate(
            {"highway": "footway"},
            {"highway": "crossing", "kerb": "raised"},
            {},
            profile,
        )[0] == (profile == Profile.stroller)
    assert evaluate({"highway": "steps"}, {}, {}, Profile.standard)[0]


def test_node_surface_does_not_document_entire_edge():
    result = evaluate(
        {"highway": "footway"}, {"surface": "asphalt"}, {}, Profile.wheelchair
    )
    assert "surface" not in result[4]
    assert "Missing surface" in result[3]
    assert result[0] and result[2] == "unknown"


def test_slopes_and_low_vision_are_distinct_and_honest():
    assert incline_percent("8.5%") == 8.5
    assert incline_percent("-10%") == 10
    assert incline_percent("up") is None
    assert (
        evaluate({"incline": "9%"}, {}, {}, Profile.wheelchair)[1]
        > evaluate({"incline": "0%"}, {}, {}, Profile.wheelchair)[1]
    )
    signals = {
        "highway": "crossing",
        "crossing": "traffic_signals",
        "traffic_signals:sound": "yes",
        "tactile_paving": "yes",
        "lit": "yes",
    }
    unmarked = {"highway": "crossing", "crossing": "unmarked"}
    assert (
        evaluate(signals, {}, {}, Profile.low_vision)[1]
        < evaluate(unmarked, {}, {}, Profile.low_vision)[1]
    )
    assert evaluate({"incline": "up"}, {}, {}, Profile.wheelchair)[2] == "concern"


def test_segments_directions_connectors_and_unknown_confidence():
    graph = nx.MultiDiGraph()
    graph.add_node(1, x=-121.9, y=37.33)
    graph.add_node(2, x=-121.9, y=37.3301)
    graph.add_edge(1, 2, length=12, name="Test Avenue", highway="footway")
    result = calculate_route(
        graph,
        (37.32999, -121.9),
        2,
        Algorithm.astar,
        Profile.wheelchair,
        {
            "stop_id": "test",
            "stop_name": "Test Stop",
            "latitude": 37.33011,
            "longitude": -121.9,
        },
    )
    assert len(result["segments"]) == 3
    assert result["data_confidence"] == 0
    assert all(s["status"] == "unknown" for s in result["segments"])
    assert result["directions"][0]["maneuver"] == "connector"
    assert "isn't on the map" in result["directions"][0]["notes"][0]
    assert "Test Avenue" in result["directions"][1]["instruction"]
    assert result["walking_speed_mps_assumed"] == 0.9
    assert sum(s["length_m"] for s in result["segments"]) == pytest.approx(
        result["distance_m"], abs=0.1
    )


def test_5000_node_route_uses_cached_spatial_index_under_budget():
    graph = nx.MultiDiGraph()
    for row in range(50):
        for column in range(100):
            node = row * 100 + column
            graph.add_node(node, y=37.3 + row * 0.0001, x=-121.9 + column * 0.0001)
            for neighbor in ([node - 1] if column else []) + (
                [node - 100] if row else []
            ):
                graph.add_edge(node, neighbor, length=12)
                graph.add_edge(neighbor, node, length=12)
    nearest_graph_node(graph, 37.3, -121.9)
    index = graph._transitgap_node_index
    started = perf_counter()
    result = calculate_route(
        graph,
        (37.3, -121.9),
        4999,
        Algorithm.astar,
        Profile.standard,
        {
            "stop_id": "grid",
            "stop_name": "Grid",
            "latitude": 37.3049,
            "longitude": -121.8901,
        },
    )
    elapsed = perf_counter() - started
    assert graph._transitgap_node_index is index
    assert result["distance_m"] > 0
    assert elapsed < 2.0, f"5000-node request took {elapsed:.3f}s"
