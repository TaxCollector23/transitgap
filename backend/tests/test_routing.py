from __future__ import annotations

import math

import networkx as nx
import pytest
from pydantic import ValidationError
from shapely.geometry import LineString, shape

import backend.app.main as main
from backend.app.models import Algorithm, Profile, RouteRequest
from backend.app.routing import _heuristic, _run, calculate_route, haversine_m


@pytest.fixture
def routing_graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    coords = {
        0: (37.32960, -121.90300),
        1: (37.32969, -121.90300),
        2: (37.32978, -121.90300),
        3: (37.32960, -121.90282),
        4: (37.33010, -121.90300),
    }
    for node, (lat, lon) in coords.items():
        graph.add_node(node, y=lat, x=lon)
    graph.add_edge(0, 1, key="west", length=11, highway="footway")
    graph.add_edge(1, 2, key="north", length=11, highway="footway")
    graph.add_edge(0, 2, key="direct", length=25, highway="footway")
    graph.add_edge(0, 3, key="east-a", length=18, highway="footway")
    graph.add_edge(3, 2, key="east-b", length=30, highway="footway")
    return graph


def test_weighted_algorithms_return_equal_optimal_costs(routing_graph):
    for profile in Profile:
        results = [_run(routing_graph, 0, 2, algorithm, profile) for algorithm in Algorithm if algorithm != Algorithm.breadth_first]
        expected = 44 if profile == Profile.prefer_documented_paths else 26.4 if profile == Profile.stroller else 31.24 if profile in {Profile.wheelchair, Profile.avoid_mapped_stairs} else 25.3 if profile == Profile.low_vision else 22
        assert [result[1] for result in results] == pytest.approx([expected] * len(results))
        assert all(path[0] == 0 and path[-1] == 2 for path, _ in results)


def test_breadth_first_optimizes_segments_instead_of_distance(routing_graph):
    path, cost = _run(routing_graph, 0, 2, Algorithm.breadth_first, Profile.standard)
    assert path == [0, 2]
    assert cost == 25  # One segment, despite the two-segment route being 22 m.
    routing_graph[0][2]["direct"]["highway"] = "steps"
    path, cost = _run(routing_graph, 0, 2, Algorithm.breadth_first, Profile.avoid_mapped_stairs)
    assert path == [0, 1, 2]
    assert cost == pytest.approx(31.24)


def test_algorithms_respect_one_way_edges(routing_graph):
    directed = nx.MultiDiGraph()
    directed.add_node(0, y=37.3296, x=-121.903)
    directed.add_node(1, y=37.3297, x=-121.903)
    directed.add_edge(0, 1, length=20)
    assert _run(directed, 0, 1, Algorithm.dijkstra, Profile.standard)[1] == 20
    for algorithm in Algorithm:
        with pytest.raises(nx.NetworkXNoPath):
            _run(directed, 1, 0, algorithm, Profile.standard)


def test_disconnected_components_and_empty_graphs_are_explicit(routing_graph):
    with pytest.raises(nx.NetworkXNoPath):
        _run(routing_graph, 0, 4, Algorithm.astar, Profile.standard)
    with pytest.raises(LookupError, match="empty"):
        calculate_route(nx.MultiDiGraph(), (37.3296, -121.903), 1,
                        Algorithm.dijkstra, Profile.standard, {})


def test_building_interior_pin_skips_nearest_disconnected_component():
    graph = nx.MultiDiGraph()
    origin = (37.33, -121.9)
    graph.add_node("interior", y=origin[0], x=origin[1])
    graph.add_node("sidewalk", y=origin[0], x=origin[1] + 0.0001)
    graph.add_node("stop", y=origin[0], x=origin[1] + 0.0002)
    graph.add_edge("sidewalk", "stop", key="walkway", length=9, highway="footway")
    stop = {"stop_id": "nearby", "stop_name": "Nearby stop", "latitude": origin[0], "longitude": origin[1] + 0.0002}

    result = calculate_route(graph, origin, "stop", Algorithm.astar, Profile.standard, stop)

    assert result["selected_edges"] == [{"from": "sidewalk", "to": "stop", "key": "walkway", "reference": '["sidewalk","stop","walkway"]'}]
    assert result["distance_m"] > 9  # the short off-network connector stays explicit in route distance


def test_origin_skips_nearest_isolated_point_for_connected_sidewalk():
    graph = nx.MultiDiGraph()
    graph.add_node("near", y=37.3296, x=-121.903)
    graph.add_node("far-a", y=37.33014, x=-121.903)
    graph.add_node("far-b", y=37.33023, x=-121.903)
    graph.add_node("far-c", y=37.33032, x=-121.903)
    graph.add_edge("far-a", "far-b", length=11)
    graph.add_edge("far-b", "far-c", length=11)
    stop = {"stop_id": "island", "stop_name": "Separate component", "latitude": 37.33023, "longitude": -121.903}
    result = calculate_route(graph, (37.3296, -121.903), "far-b", Algorithm.dijkstra, Profile.standard, stop)
    assert result["accessibility"]["selected_edge_keys"][0]["from"] == "far-a"
    assert result["accessibility"]["selected_edge_keys"][0]["to"] == "far-b"
    assert result["distance_m"] > graph["far-a"]["far-b"][0]["length"]


def test_parallel_edges_keep_selected_key_and_curved_geometry():
    graph = nx.MultiDiGraph()
    graph.add_node("a", y=37.32960, x=-121.90300)
    graph.add_node("b", y=37.32980, x=-121.90300)
    # The shorter edge is a stair with an unmistakable curved path. The
    # documented alternate has a different key, cost, and geometry orientation.
    stair = LineString([(-121.90300, 37.32980), (-121.90296, 37.32970), (-121.90300, 37.32960)])
    ramp = LineString([(-121.90300, 37.32980), (-121.90288, 37.32970), (-121.90300, 37.32960)])
    def geometry_length(line):
        points = list(line.coords)
        return sum(haversine_m((points[i - 1][1], points[i - 1][0]), (points[i][1], points[i][0]))
                   for i in range(1, len(points)))
    graph.add_edge("a", "b", key="stair-shape", length=geometry_length(stair), highway="steps", geometry=stair)
    graph.add_edge("a", "b", key="documented-ramp", length=geometry_length(ramp), highway="footway", geometry=ramp,
                   surface="asphalt", smoothness="good", incline="0%", wheelchair="yes")
    stop = {"stop_id": "fixture", "stop_name": "Fixture stop", "latitude": 37.32980, "longitude": -121.903}

    shortest = calculate_route(graph, (37.32960, -121.903), "b", Algorithm.dijkstra, Profile.standard, stop)
    stairs_avoided = calculate_route(graph, (37.32960, -121.903), "b", Algorithm.bidirectional_dijkstra,
                                     Profile.avoid_mapped_stairs, stop)
    documented = calculate_route(graph, (37.32960, -121.903), "b", Algorithm.astar,
                                  Profile.prefer_documented_paths, stop)
    assert shortest["accessibility"]["selected_edge_keys"][0]["key"] == "stair-shape"
    assert stairs_avoided["accessibility"]["selected_edge_keys"][0]["key"] == "documented-ramp"
    assert documented["accessibility"]["selected_edge_keys"][0]["key"] == "documented-ramp"
    assert len(shape(shortest["geometry"]).coords) == 3
    assert shape(stairs_avoided["geometry"]).coords[0] == pytest.approx((-121.90300, 37.32960))
    assert shape(stairs_avoided["geometry"]).is_valid
    assert stairs_avoided["distance_m"] == pytest.approx(geometry_length(ramp), abs=0.1)
    assert shortest["distance_m"] == pytest.approx(geometry_length(stair), abs=0.1)
    assert documented["optimization_cost_m"] >= documented["distance_m"] - 0.1
    assert stairs_avoided["mapped_stair_segments"] == 0


def test_access_restrictions_hide_only_the_prohibited_edge(routing_graph):
    routing_graph.add_edge(0, 2, key="private-shortcut", length=1, access="private")
    path, cost = _run(routing_graph, 0, 2, Algorithm.dijkstra, Profile.standard)
    assert path == [0, 1, 2]
    assert cost == 22
    routing_graph.add_edge(0, 2, key="foot-override", length=5, access="private", foot="yes")
    path, cost = _run(routing_graph, 0, 2, Algorithm.dijkstra, Profile.standard)
    assert path == [0, 2]
    assert cost == 5
    routing_graph.nodes[2]["foot"] = "no"
    with pytest.raises(nx.NetworkXNoPath):
        _run(routing_graph, 0, 2, Algorithm.dijkstra, Profile.standard)


@pytest.mark.parametrize("length", [-1, float("nan"), float("inf")])
def test_invalid_edge_lengths_are_rejected(routing_graph, length):
    routing_graph.add_edge(0, 4, key="bad", length=length)
    with pytest.raises(ValueError, match="invalid or negative length"):
        _run(routing_graph, 0, 4, Algorithm.dijkstra, Profile.standard)


def test_missing_length_uses_edge_geometry_and_nonfinite_input_is_rejected(routing_graph):
    graph = nx.MultiDiGraph()
    graph.add_node(0, y=37.3296, x=-121.903)
    graph.add_node(1, y=37.3297, x=-121.903)
    graph.add_edge(0, 1, geometry=LineString([(-121.903, 37.3296), (-121.903, 37.32965), (-121.903, 37.3297)]))
    assert _run(graph, 0, 1, Algorithm.dijkstra, Profile.standard)[1] == pytest.approx(haversine_m((37.3296, -121.903), (37.3297, -121.903)))
    with pytest.raises(ValueError, match="finite"):
        calculate_route(graph, (math.nan, -121.903), 1, Algorithm.dijkstra, Profile.standard, {})
    with pytest.raises(ValidationError):
        RouteRequest(origin_latitude=math.nan, origin_longitude=-121.9, destination_stop_id="stop")


def test_unreasonable_origin_snap_is_rejected(routing_graph):
    stop = {"stop_id": "fixture", "stop_name": "Fixture stop", "latitude": 37.32978, "longitude": -121.903}
    with pytest.raises(ValueError, match="from a mapped walking path"):
        calculate_route(routing_graph, (37.332, -121.903), 2,
                        Algorithm.dijkstra, Profile.standard, stop)


def test_misaligned_stored_geometry_is_rejected_instead_of_drawn_as_a_chord():
    graph = nx.MultiDiGraph()
    graph.add_node(0, y=37.3296, x=-121.903)
    graph.add_node(1, y=37.3297, x=-121.903)
    graph.add_edge(0, 1, length=12, geometry=LineString([(-121.9, 37.3296), (-121.9, 37.3297)]))
    stop = {"stop_id": "fixture", "stop_name": "Fixture stop", "latitude": 37.3297, "longitude": -121.903}
    with pytest.raises(ValueError, match="does not meet its graph-node endpoints"):
        calculate_route(graph, (37.3296, -121.903), 1,
                        Algorithm.dijkstra, Profile.standard, stop)


def test_geographic_heuristic_never_exceeds_route_cost(routing_graph):
    for u, v, attrs in routing_graph.edges(data=True):
        lower_bound = _heuristic(routing_graph, u, v)
        assert lower_bound <= attrs["length"] + 1e-6


def test_route_distance_and_geojson_match_selected_edge_geometry(routing_graph):
    stop = {"stop_id": "fixture", "stop_name": "Fixture stop", "latitude": 37.32978, "longitude": -121.903}
    result = calculate_route(routing_graph, (37.32960, -121.903), 2,
                             Algorithm.dijkstra, Profile.standard, stop)
    geometry = shape(result["geometry"])
    assert result["geometry"]["type"] == "LineString"
    assert geometry.is_valid and len(geometry.coords) >= 3
    assert result["distance_m"] == pytest.approx(22.0, abs=0.2)
    assert result["optimization_cost_m"] == pytest.approx(22.0, abs=0.2)
    assert result["accessibility"]["distance_denominator_m"] == 22


def test_route_request_rejects_invalid_ranges_and_missing_fields():
    with pytest.raises(ValidationError):
        RouteRequest(origin_latitude=120, origin_longitude=-121.9, destination_stop_id="stop")
    with pytest.raises(ValidationError):
        RouteRequest(origin_latitude=37.3, origin_longitude=-121.9)


@pytest.mark.integration
def test_real_cached_vta_osm_api_contract(client):
    health = client.get("/health")
    assert health.status_code == 200 and health.json()["ready"] is True
    coverage = client.get("/coverage").json()
    stops_response = client.get("/stops")
    assert stops_response.status_code == 200
    stops = stops_response.json()["stops"]
    assert stops_response.json()["count"] == len(stops) > 0
    stop = next(item for item in stops if "Bay 11" in item["stop_name"])
    request = {"origin_latitude": 37.32875, "origin_longitude": -121.90442,
               "destination_stop_id": stop["stop_id"]}
    for algorithm in Algorithm:
        for profile in Profile:
            response = client.post("/route", json={**request, "algorithm": algorithm.value, "profile": profile.value})
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["geometry"]["type"] == "LineString"
            assert data["distance_m"] > 0
            assert data["optimization_cost_m"] >= 0
            assert data["accessibility"]["distance_denominator_m"] >= 0
            assert data["optimization_objective"]
            assert data["destination"]["stop_id"] == stop["stop_id"]
    outside = client.post("/route", json={**request, "origin_latitude": 37.8, "origin_longitude": -122.4})
    assert outside.status_code == 422
    missing_stop = client.post("/route", json={**request, "destination_stop_id": "not-a-vta-stop"})
    assert missing_stop.status_code == 404
    invalid_coordinate = client.post("/route", json={**request, "origin_latitude": "NaN"})
    assert invalid_coordinate.status_code == 422


@pytest.mark.integration
def test_real_route_comparison_returns_every_objective(client):
    response = client.post("/route/compare", json={"origin_latitude": 37.32875,
                             "origin_longitude": -121.90442, "destination_stop_id": "4514"})
    assert response.status_code == 200, response.text
    comparison = response.json()
    assert [item["profile"] for item in comparison["results"]] == [profile.value for profile in Profile]
    assert all(item["objective"] for item in comparison["results"])
    assert all(item["available"] and item["route"]["optimization_cost_m"] >= 0
               for item in comparison["results"])


@pytest.mark.integration
def test_comparison_marks_missing_profile_route_unavailable(client, monkeypatch):
    stop = next(item for item in main.state["stops"] if "Bay 11" in item["stop_name"])
    real_calculate = main.calculate_route

    def one_profile_unavailable(graph, origin, destination, algorithm, profile, selected_stop):
        if profile == Profile.avoid_mapped_stairs:
            raise LookupError("No path without mapped stairs")
        return real_calculate(graph, origin, destination, algorithm, profile, selected_stop)

    monkeypatch.setattr(main, "calculate_route", one_profile_unavailable)
    response = client.post("/route/compare", json={
        "origin_latitude": 37.32875,
        "origin_longitude": -121.90442,
        "destination_stop_id": stop["stop_id"],
    })
    assert response.status_code == 200
    results = {item["profile"]: item for item in response.json()["results"]}
    assert results[Profile.standard.value]["available"] is True
    assert results[Profile.avoid_mapped_stairs.value]["available"] is False
    assert results[Profile.avoid_mapped_stairs.value]["route"] is None
    assert results[Profile.avoid_mapped_stairs.value]["error"] == "No path without mapped stairs"
    assert results[Profile.prefer_documented_paths.value]["available"] is True


def test_astar_matches_dijkstra_when_stored_lengths_are_shorter_than_geographic_distance():
    graph=nx.MultiDiGraph()
    for node,x in [('o',0),('x',1),('s',.001)]:graph.add_node(node,x=x,y=0)
    graph.add_edge('o','s',length=10)
    graph.add_edge('o','x',length=1)
    graph.add_edge('x','s',length=1)
    for algorithm in (Algorithm.astar, Algorithm.dijkstra):
        assert _run(graph,'o','s',algorithm,Profile.standard)==(['o','x','s'],2.0)
