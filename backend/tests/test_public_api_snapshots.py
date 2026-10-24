from __future__ import annotations

from backend.app import main
from backend.app.public_api_snapshots import write_public_api_snapshots


class EvidenceIndex:
    gaps = [{"id": f"gap:{number}"} for number in range(5)]

    def source_status(self):
        return {"sources": [{"id": "osm", "status": "ready"}], "generated_at": "build-time"}

    def get_priorities(self, limit=50, offset=0):
        candidates = [{"id": item["id"]} for item in self.gaps[offset : offset + limit]]
        return {
            "count": len(self.gaps),
            "limit": limit,
            "offset": offset,
            "candidates": candidates,
            "generated_at": "build-time",
        }


def test_data_sources_are_available_before_graph_initialization(tmp_path, monkeypatch):
    write_public_api_snapshots(
        tmp_path,
        EvidenceIndex(),
        {
            "caltrain": {
                "name": "Caltrain",
                "developer_url": "https://example.org/caltrain",
                "feed_url": "https://example.org/caltrain.zip",
                "stop_count": 34,
                "feed_info": {"feed_version": "test"},
            }
        },
    )
    monkeypatch.setattr(main, "data_dir", lambda: tmp_path)
    monkeypatch.setitem(main.state, "groundtruth", None)
    monkeypatch.setattr(main, "_groundtruth", lambda: (_ for _ in ()).throw(AssertionError("graph index used")))

    result = main.data_sources()

    assert result["sources"][0]["id"] == "osm"
    assert next(source for source in result["sources"] if source["id"] == "caltrain-gtfs")["feature_count"] == 34


def test_priorities_are_available_before_graph_initialization_and_keep_pagination(tmp_path, monkeypatch):
    write_public_api_snapshots(tmp_path, EvidenceIndex(), {})
    monkeypatch.setattr(main, "data_dir", lambda: tmp_path)
    monkeypatch.setitem(main.state, "groundtruth", None)
    monkeypatch.setattr(main, "_groundtruth", lambda: (_ for _ in ()).throw(AssertionError("graph index used")))

    first_page = main.accessibility_priorities(limit=2, offset=0)
    second_page = main.accessibility_priorities(limit=2, offset=2)

    assert first_page["count"] == 5
    assert first_page["limit"] == 2 and first_page["offset"] == 0
    assert [item["id"] for item in first_page["candidates"]] == ["gap:0", "gap:1"]
    assert [item["id"] for item in second_page["candidates"]] == ["gap:2", "gap:3"]


def test_reachability_stop_list_is_available_before_graph_initialization(tmp_path, monkeypatch):
    snapshot = {
        "study_area": {"name": "Diridon Station pilot", "radius_m": 1500},
        "stop_count": 1,
        "stops": [{
            "stop_id": "test-stop",
            "stop_name": "Test & 1st",
            "latitude": 37.33,
            "longitude": -121.90,
            "connector_distance_m": 12.0,
        }],
        "source": "Prepared from the VTA GTFS and mapped walking graph.",
    }
    write_public_api_snapshots(tmp_path, EvidenceIndex(), {}, reachability_stops=snapshot)
    monkeypatch.setattr(main, "data_dir", lambda: tmp_path)
    monkeypatch.setitem(main.state, "graph", None)
    monkeypatch.setitem(main.state, "stops", [])
    monkeypatch.setattr(
        main,
        "_reachability_study",
        lambda: (_ for _ in ()).throw(AssertionError("graph-backed study used")),
    )

    assert main.reachability_stops() == snapshot

