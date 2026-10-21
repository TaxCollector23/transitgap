"""Synthetic-graph checks for rider-facing maneuver grouping."""
from math import cos, radians

import networkx as nx
import pytest

from backend.app.directions import directions
from backend.app.models import Algorithm, Profile
from backend.app.routing import calculate_route

LAT0, LON0 = 37.33, -121.90


def at(east_m: float, north_m: float) -> tuple[float, float]:
    """(x, y) for a point offset in meters from a fixed San Jose origin."""
    return (LON0 + east_m / (111_320 * cos(radians(LAT0))), LAT0 + north_m / 111_320)


class Builder:
    def __init__(self):
        self.graph = nx.MultiDiGraph()

    def node(self, name, east, north, **tags):
        x, y = at(east, north)
        self.graph.add_node(name, x=x, y=y, **tags)

    def way(self, nodes, both=True, **tags):
        for u, v in zip(nodes, nodes[1:]):
            self.graph.add_edge(u, v, **tags)
            if both:
                self.graph.add_edge(v, u, **tags)

    def stop(self, node, name="Test Stop"):
        data = self.graph.nodes[node]
        return {"stop_id": "t", "stop_name": name, "latitude": data["y"], "longitude": data["x"]}

    def route(self, start, end, profile=Profile.standard, origin=None):
        data = self.graph.nodes[start]
        origin = origin or (data["y"], data["x"])
        return calculate_route(self.graph, origin, end, Algorithm.dijkstra, profile, self.stop(end))


def walking(result):
    return [step for step in result["directions"] if step["maneuver"] != "arrive"]


def assert_distance_preserved(result):
    total = sum(step["distance_m"] for step in result["directions"])
    assert total == pytest.approx(result["distance_m"], abs=0.5)
    covered = [i for step in walking(result) for i in range(step["segment_range"][0], step["segment_range"][1] + 1)]
    assert covered == list(range(len(result["segments"])))


def no_jargon(result):
    for step in result["directions"]:
        assert "unnamed" not in step["instruction"].lower()
        assert "information missing" not in step["instruction"].lower()


def test_continuous_unnamed_footway_split_into_many_edges_is_one_step():
    b = Builder()
    for i in range(11):
        b.node(i, i * 30, 0)
    b.way(list(range(11)), highway="footway")
    result = b.route(0, 10)
    steps = walking(result)
    assert len(result["segments"]) == 10
    assert len(steps) == 1
    assert steps[0]["instruction"] == "Head east along the pedestrian path"
    assert result["directions"][-1]["instruction"] == "Arrive at Test Stop"
    assert_distance_preserved(result)
    no_jargon(result)


def test_named_streets_turn_onto_supported_name_only():
    b = Builder()
    for i in range(4):
        b.node(f"b{i}", i * 60, 0)
    b.node("n1", 180, 60)
    b.node("n2", 180, 120)
    b.node("side", 60, -60)  # a real side street makes b1 a junction
    b.way(["b0", "b1", "b2", "b3"], highway="residential", name="Benton Street")
    b.way(["b3", "n1", "n2"], highway="residential", name="Lincoln Street")
    b.way(["b1", "side"], highway="residential")
    result = b.route("b0", "n2")
    steps = walking(result)
    assert [s["instruction"] for s in steps] == ["Head east on Benton Street", "Turn left onto Lincoln Street"]
    assert_distance_preserved(result)


def test_unnamed_sidewalks_never_borrow_a_road_name():
    b = Builder()
    for i in range(3):
        b.node(f"r{i}", i * 50, 0)
        b.node(f"s{i}", i * 50, 8)
    b.way(["r0", "r1", "r2"], highway="residential", name="Benton Street")
    b.way(["s0", "s1", "s2"], highway="footway", footway="sidewalk")
    result = b.route("s0", "s2")
    assert walking(result)[0]["instruction"] == "Head east along the sidewalk"
    assert all("Benton" not in s["instruction"] for s in result["directions"])


def test_genuine_intersection_is_a_turn_but_a_forced_bend_is_not():
    b = Builder()
    b.node("a", 0, 0); b.node("j", 80, 0); b.node("south", 80, -80); b.node("east", 160, 0)
    b.way(["a", "j"], highway="footway", footway="sidewalk")
    b.way(["j", "south"], highway="footway", footway="sidewalk")
    b.way(["j", "east"], highway="footway", footway="sidewalk")
    turned = b.route("a", "south")
    assert [s["maneuver"] for s in walking(turned)] == ["depart", "turn-right"]
    assert walking(turned)[1]["instruction"] == "Turn right onto the sidewalk heading south"

    bend = Builder()
    bend.node("a", 0, 0); bend.node("corner", 80, 0); bend.node("b", 80, -80)
    bend.way(["a", "corner"], highway="footway")
    bend.way(["corner", "b"], highway="footway")
    assert len(walking(bend.route("a", "b"))) == 1


def test_curving_named_road_is_one_maneuver():
    from math import pi, sin
    b = Builder()
    points = [(200 * sin(t * pi / 2 / 12), 200 - 200 * cos(t * pi / 2 / 12)) for t in range(13)]
    for i, (east, north) in enumerate(points):
        b.node(i, east, north)
    b.way(list(range(13)), highway="residential", name="Curve Road")
    result = b.route(0, 12)
    assert len(walking(result)) == 1
    assert walking(result)[0]["instruction"] == "Head east on Curve Road, then follow it as it curves north"
    assert_distance_preserved(result)


def test_very_short_segments_and_small_jogs_do_not_become_steps():
    b = Builder()
    b.node("a", 0, 0); b.node("b", 60, 0); b.node("c", 61, 0); b.node("d", 62.5, 3)
    b.node("e", 63, 3); b.node("f", 140, 3); b.node("spur", 61, -40)
    b.way(["a", "b", "c"], highway="footway", footway="sidewalk")
    b.way(["c", "d", "e"], highway="footway", footway="sidewalk")
    b.way(["e", "f"], highway="footway", footway="sidewalk")
    b.way(["c", "spur"], highway="footway")
    result = b.route("a", "f")
    steps = walking(result)
    assert len(steps) == 1
    assert all(step["distance_m"] > 0 for step in steps)
    assert_distance_preserved(result)


def test_repeated_osm_way_and_parallel_edges_keep_one_step_and_shortest_edge():
    b = Builder()
    for i in range(5):
        b.node(i, i * 40, 0)
    b.way(list(range(5)), highway="footway", osmid=77)
    b.graph.add_edge(1, 2, highway="footway", osmid=78, length=400)
    result = b.route(0, 4)
    assert len(walking(result)) == 1
    assert result["distance_m"] == pytest.approx(160, abs=1)
    assert_distance_preserved(result)


def test_straight_crossing_is_a_note_and_turning_crossing_is_a_step():
    b = Builder()
    b.node("a", 0, 0); b.node("k1", 80, 0); b.node("k2", 92, 0); b.node("z", 180, 0)
    b.node("spur", 80, 40)
    b.way(["a", "k1"], highway="footway", footway="sidewalk")
    b.way(["k1", "k2"], highway="footway", footway="crossing", crossing="unmarked")
    b.way(["k2", "z"], highway="footway", footway="sidewalk")
    b.way(["k1", "spur"], highway="footway", footway="sidewalk")
    straight = b.route("a", "z")
    steps = walking(straight)
    assert len(steps) == 1
    assert steps[0]["crossings"]["total"] == 1 and steps[0]["crossings"]["unmarked"] == 1
    assert steps[0]["notes"] == ["Includes 1 mapped crossing along the way; 1 is mapped as unmarked."]
    assert "Mapped unmarked crossing" not in steps[0]["documented_concerns"]

    t = Builder()
    t.node("a", 0, 0); t.node("c0", 80, 0); t.node("c1", 80, 14); t.node("n", 80, 100); t.node("e", 160, 0)
    t.way(["a", "c0"], highway="footway", footway="sidewalk")
    t.way(["c0", "e"], highway="footway", footway="sidewalk")
    t.way(["c0", "c1"], highway="footway", footway="crossing", crossing="traffic_signals")
    t.way(["c1", "n"], highway="footway", footway="sidewalk")
    turned = t.route("a", "n")
    steps = walking(turned)
    assert steps[1]["instruction"] == "Turn left and cross the street, then continue along the sidewalk"
    assert "This crossing is mapped with traffic signals." in steps[1]["notes"]
    assert_distance_preserved(turned)


def test_stairs_are_their_own_step_and_wheelchair_takes_the_documented_detour():
    b = Builder()
    b.node("a", 0, 0); b.node("s0", 50, 0); b.node("s1", 70, 0); b.node("z", 120, 0)
    b.node("r", 60, -40)
    b.way(["a", "s0"], highway="footway")
    b.way(["s0", "s1"], highway="steps")
    b.way(["s1", "z"], highway="footway")
    b.way(["s0", "r", "s1"], highway="footway", surface="asphalt")
    standard = b.route("a", "z")
    kinds = [s["maneuver"] for s in walking(standard)]
    assert "steps" in kinds
    stairs = next(s for s in walking(standard) if s["maneuver"] == "steps")
    assert stairs["instruction"] == "Take the stairs"
    assert stairs["warnings"] == ["Stairs are mapped here."]
    assert standard["accessibility_summary"]["documented_restrictions"][0]["code"] == "Mapped stairs"

    wheelchair = b.route("a", "z", profile=Profile.wheelchair)
    assert wheelchair["distance_m"] > standard["distance_m"]
    assert all(s["maneuver"] != "steps" for s in wheelchair["directions"])
    assert_distance_preserved(standard)
    assert_distance_preserved(wheelchair)


def test_unmapped_connectors_are_never_walking_instructions():
    b = Builder()
    b.node("a", 0, 0); b.node("z", 120, 0)
    b.way(["a", "z"], highway="footway")
    origin = at(0, -30)
    result = calculate_route(b.graph, (origin[1], origin[0]), "z", Algorithm.dijkstra, Profile.wheelchair,
                             {"stop_id": "t", "stop_name": "Test Stop", "latitude": at(130, 0)[1], "longitude": at(130, 0)[0]})
    steps = walking(result)
    assert steps[0]["maneuver"] == "connector" and not steps[0]["instruction"].startswith("Head")
    assert steps[1]["instruction"].startswith("Head east")
    assert steps[-1]["maneuver"] == "connector" and "Test Stop" in steps[-1]["instruction"]
    summary = result["accessibility_summary"]
    assert [c["position"] for c in summary["unmapped_connectors"]] == ["start", "end"]
    assert result["geometry_audit"]["continuous"]
    assert_distance_preserved(result)


def test_missing_information_is_summarized_once_not_per_step():
    b = Builder()
    for i in range(6):
        b.node(i, i * 50, 0)
    b.node("x", 100, 50)
    b.way(list(range(6)), highway="footway")
    b.way([2, "x"], highway="footway")
    result = b.route(0, 5, profile=Profile.wheelchair)
    summary = result["accessibility_summary"]
    assert summary["headline"] == "Some accessibility information is missing along this route."
    assert {item["attribute"] for item in summary["missing_information"]} >= {"surface", "width"}
    assert all(step["warnings"] == [] for step in walking(result))
    assert "Missing surface" in result["segments"][0]["reasons"]  # edge evidence preserved


def test_legacy_segments_without_kind_still_group():
    segments = [
        {"geometry": {"type": "LineString", "coordinates": [list(at(i * 20, 0)), list(at((i + 1) * 20, 0))]},
         "length_m": 20.0, "status": "unknown", "reasons": ["Missing surface"], "name": None}
        for i in range(8)
    ]
    steps = directions(segments)
    assert len(steps) == 1 and steps[0]["distance_m"] == 160


def test_same_named_street_bend_is_not_a_step_but_a_real_turn_says_stay_on():
    b = Builder()
    b.node("a", 0, 0); b.node("j", 100, 0); b.node("k", 180, 25); b.node("x", 100, -60)
    b.node("t", 260, 25); b.node("u", 260, 120); b.node("y", 340, 25)
    b.way(["a", "j", "k", "t"], highway="residential", name="Timothy Drive")
    b.way(["j", "x"], highway="residential")
    b.way(["t", "u"], highway="residential", name="Timothy Drive")
    b.way(["t", "y"], highway="residential", name="Other Street")
    bend = b.route("a", "t")
    assert [s["instruction"] for s in walking(bend)] == ["Head east on Timothy Drive"]
    corner = b.route("a", "u")
    assert [s["instruction"] for s in walking(corner)] == ["Head east on Timothy Drive", "Turn left to stay on Timothy Drive"]


def test_crossing_nodes_and_edges_close_together_count_as_one_crossing():
    b = Builder()
    b.node("a", 0, 0); b.node("k1", 60, 0, highway="crossing", crossing="unmarked")
    b.node("k2", 66, 0); b.node("k3", 78, 0, highway="crossing")
    b.node("z", 200, 0); b.node("far", 150, 0, highway="crossing", crossing="marked")
    b.node("spur", 60, 30)
    b.way(["a", "k1", "k2"], highway="footway", footway="sidewalk")
    b.way(["k2", "k3"], highway="footway", footway="crossing", crossing="unmarked")
    b.way(["k3", "far", "z"], highway="footway", footway="sidewalk")
    b.way(["k1", "spur"], highway="footway")
    steps = walking(b.route("a", "z"))
    assert len(steps) == 1
    assert steps[0]["crossings"]["total"] == 2
    assert steps[0]["crossings"]["unmarked"] == 1 and steps[0]["crossings"]["marked"] == 1


def test_heading_of_a_short_step_is_measured_within_that_step():
    b = Builder()
    b.node("a", 0, 0); b.node("j", 0, 100); b.node("k", -17, 100); b.node("z", -17, 200)
    b.node("x", 50, 100); b.node("y", -17, 60)
    b.way(["a", "j"], highway="service")
    b.way(["j", "k"], highway="service")
    b.way(["k", "z"], highway="footway", footway="sidewalk")
    b.way(["j", "x"], highway="service")
    b.way(["k", "y"], highway="service")
    steps = walking(b.route("a", "z"))
    assert steps[1]["instruction"] == "Turn left onto the service road heading west"
    assert steps[2]["instruction"] == "Turn right onto the sidewalk heading north"
