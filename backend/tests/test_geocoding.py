import pytest
from shapely.geometry import box
from backend.app import geocoding


def test_geocoder_is_bounded_cached_and_not_autocomplete(monkeypatch):
    calls = []

    class FakeClient:
        def __init__(self, **kwargs):
            assert "TransitGap" in kwargs["headers"]["User-Agent"]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url, params):
            calls.append(params)
            if params["q"] == "Union Station, Los Angeles":
                results = [{"display_name": "Union Station, Los Angeles", "lat": "34.056", "lon": "-118.236"}]
            elif params["q"] == "gibberish xyz":
                results = []
            else:
                results = [
                    {"display_name": "Inside", "lat": "37.33", "lon": "-121.9"},
                    {"display_name": "Outside", "lat": "0", "lon": "0"},
                ]
            return type(
                "Response",
                (),
                {
                    "raise_for_status": lambda self: None,
                    "json": lambda self: results,
                },
            )()

    monkeypatch.setattr(geocoding.httpx, "Client", FakeClient)
    geocoding._cache.clear()
    monkeypatch.setattr(geocoding, "_last_request", 0)
    area = box(-122, 37, -121, 38)
    result = geocoding.search("Some place", area)
    assert len(result["results"]) == 1
    assert geocoding.search("Some place", area) == result
    assert len(calls) == 1 and "viewbox" in calls[0] and "bounded" not in calls[0]
    geocoding._last_request = -5
    outside = geocoding.search("Union Station, Los Angeles", area)
    assert outside["results"] == [] and outside["reason"] == "outside_coverage"
    geocoding._last_request = -5
    missing = geocoding.search("gibberish xyz", area)
    assert missing["results"] == [] and missing["reason"] is None
    with pytest.raises(RuntimeError):
        geocoding.search("Another place", area)
    with pytest.raises(ValueError):
        geocoding.search("ab", area)
