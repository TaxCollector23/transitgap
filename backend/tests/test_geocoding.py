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
            return type(
                "Response",
                (),
                {
                    "raise_for_status": lambda self: None,
                    "json": lambda self: [
                        {"display_name": "Inside", "lat": "37.33", "lon": "-121.9"},
                        {"display_name": "Outside", "lat": "0", "lon": "0"},
                    ],
                },
            )()

    monkeypatch.setattr(geocoding.httpx, "Client", FakeClient)
    geocoding._cache.clear()
    monkeypatch.setattr(geocoding, "_last_request", 0)
    area = box(-122, 37, -121, 38)
    result = geocoding.search("Some place", area)
    assert len(result["results"]) == 1
    assert geocoding.search("Some place", area) == result
    assert len(calls) == 1 and calls[0]["bounded"] == 1
    with pytest.raises(RuntimeError):
        geocoding.search("Another place", area)
    with pytest.raises(ValueError):
        geocoding.search("ab", area)
