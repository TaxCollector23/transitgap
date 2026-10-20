from __future__ import annotations

import pytest

from backend.app.accessibility import analyze_route, edge_uncertainty, uncertainty_penalties
from backend.app.models import Profile


def test_uncertainty_penalty_is_deterministic_and_based_only_on_missing_fields():
    unknown = {"highway": "footway"}
    known = {"highway": "footway", "surface": "asphalt", "smoothness": "good",
             "incline": "0%", "wheelchair": "yes", "width": "2.0"}
    weights = uncertainty_penalties()
    first = edge_uncertainty(unknown, {}, {}, Profile.prefer_documented_paths, weights)
    second = edge_uncertainty(unknown, {}, {}, Profile.prefer_documented_paths, weights)
    assert first == second
    assert first[0] == pytest.approx(weights["surface"] + weights["smoothness"] + weights["incline"] + weights["wheelchair"] + weights["width"])
    assert first[2] == ["surface", "smoothness", "incline", "wheelchair", "width"]
    assert edge_uncertainty(known, {}, {}, Profile.prefer_documented_paths, weights) == (0.0, ["surface", "smoothness", "incline", "wheelchair", "width"], [])
    assert edge_uncertainty(unknown, {}, {}, Profile.standard, weights)[0] == 0.0


@pytest.mark.parametrize("value", ["-0.1", "nan", "inf", "not-a-number"])
def test_uncertainty_weights_reject_negative_and_nonfinite_configuration(monkeypatch, value):
    monkeypatch.setenv("TRANSITGAP_UNCERTAINTY_PENALTY_SURFACE", value)
    with pytest.raises(ValueError, match="finite nonnegative"):
        uncertainty_penalties()


def test_configured_weights_are_used_and_only_applicable_fields_are_penalized(monkeypatch):
    monkeypatch.setenv("TRANSITGAP_UNCERTAINTY_PENALTY_SURFACE", "0.7")
    weights = uncertainty_penalties()
    road = {"highway": "residential", "surface": "asphalt"}
    _, _, missing_road = edge_uncertainty(road, {}, {}, Profile.prefer_documented_paths, weights)
    footway = {"highway": "footway"}
    _, _, missing_footway = edge_uncertainty(footway, {}, {}, Profile.prefer_documented_paths, weights)
    assert "sidewalk" in missing_road
    assert "sidewalk" not in missing_footway
    assert weights["surface"] == 0.7
    assert edge_uncertainty(footway, {}, {}, Profile.prefer_documented_paths, weights)[0] >= 0.7
    with pytest.raises(ValueError, match="finite nonnegative"):
        edge_uncertainty(footway, {}, {}, Profile.prefer_documented_paths, {"surface": -1})


def test_crossing_node_tags_are_relevant_once_and_barriers_are_deduplicated():
    crossing = {"highway": "crossing", "crossing": "marked", "kerb": "lowered", "tactile_paving": "yes", "barrier": "bollard"}
    path = [
        {"data": {"highway": "footway", "surface": "paved"}, "start": {}, "end": crossing,
         "start_id": "1", "end_id": "cross", "key": 0, "length_m": 10},
        {"data": {"highway": "footway"}, "start": crossing, "end": {},
         "start_id": "cross", "end_id": "2", "key": 0, "length_m": 10},
    ]
    report = analyze_route(path)
    assert report["crossing_observations"] == {
        "known_kerb_information": 1, "unknown_kerb_information": 0, "denominator": 1,
    }
    assert report["known_mapped_barrier_count"] == 1
    assert report["surface_distance_known_m"] == 10
    assert report["surface_distance_missing_m"] == 10
    assert report["distance_denominator_m"] == 20
    assert "surface" in [item["attribute"] for item in report["missing_attributes"]]
    assert report["source"].startswith("OpenStreetMap")


def test_ordinary_walk_segment_does_not_require_crossing_or_kerb_tags():
    report = analyze_route([{"data": {"highway": "footway"}, "start": {}, "end": {},
                            "start_id": "1", "end_id": "2", "key": 0, "length_m": 5}])
    missing = {item["attribute"] for item in report["missing_attributes"]}
    assert "kerb" not in missing
    assert "crossing" not in missing
