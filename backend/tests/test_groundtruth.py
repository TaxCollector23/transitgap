from backend.app.groundtruth import MATCH_DISTANCE_M, REVIEW_DISTANCE_M, _comparison_status


def test_near_explicit_path_is_correspondence_not_accessibility_proof():
    city = {"id": "city:1"}
    nearby = [(MATCH_DISTANCE_M - 0.1, {"id": "osm:1"})]
    assert _comparison_status(city, nearby) == "DOCUMENTED_IN_MULTIPLE_SOURCES"


def test_offset_inside_review_band_needs_review():
    city = {"id": "city:2"}
    nearby = [(MATCH_DISTANCE_M + 0.1, {"id": "osm:2"})]
    assert _comparison_status(city, nearby) == "NEEDS_REVIEW"


def test_distinct_parallel_paths_are_ambiguous():
    city = {"id": "city:3"}
    nearby = [(1.0, {"id": "osm:left"}), (2.0, {"id": "osm:right"})]
    assert _comparison_status(city, nearby) == "NEEDS_REVIEW"


def test_opposite_side_beyond_review_tolerance_is_city_only():
    city = {"id": "city:4"}
    nearby = [(REVIEW_DISTANCE_M + 0.1, {"id": "osm:opposite-side"})]
    assert _comparison_status(city, nearby) == "DOCUMENTED_IN_CITY_ONLY"


def test_city_feature_with_no_nearby_osm_path_is_city_only():
    assert _comparison_status({"id": "city:placeholder"}, []) == "DOCUMENTED_IN_CITY_ONLY"


def test_invalid_geometry_repair_uses_shapely_make_valid():
    # Bow-tie polygon illustrates the self-intersection that the ingest path repairs.
    from shapely.geometry import Polygon
    from shapely import make_valid

    invalid = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
    assert not invalid.is_valid
    assert make_valid(invalid).is_valid
