from types import SimpleNamespace
import anyio
import networkx as nx
import pytest
from fastapi import HTTPException
from mcp import Client
from backend.app import main
from backend.app.gaps import GapIndex
from backend.app.models import RouteComparisonRequest
from backend.app.mcp_server import server


@pytest.fixture
def study(tmp_path, monkeypatch):
    graph = nx.MultiDiGraph()
    graph.add_node(1, x=-121.903, y=37.3296)
    graph.add_node(2, x=-121.903, y=37.3297)
    graph.add_node(3, x=-121.9029, y=37.32965)
    for a, b, length, kind in (
        (1, 2, 12, "steps"),
        (1, 3, 13, "footway"),
        (3, 2, 13, "footway"),
    ):
        graph.add_edge(a, b, length=length, highway=kind, name="Fixture path")
        graph.add_edge(b, a, length=length, highway=kind, name="Fixture path")
    stops = [
        {
            "stop_id": "s",
            "stop_name": "Fixture Stop",
            "latitude": 37.3297,
            "longitude": -121.903,
            "graph_node": 2,
            "wheelchair_boarding": 0,
        }
    ]
    gaps = GapIndex(graph, stops, tmp_path)
    gaps.prepare(1)
    for k, v in {
        "graph": graph,
        "stops": stops,
        "transit_stops": stops,
        "gaps": gaps,
        "schedule": None,
        "region": "diridon",
        "radius_m": 1500,
        "groundtruth": None,
    }.items():
        monkeypatch.setitem(main.state, k, v)
    return graph


def test_compare_reports_real_detour_and_explicit_speed_assumptions(study):
    response = main.mobility_comparison(
        RouteComparisonRequest(
            origin_latitude=37.3296,
            origin_longitude=-121.903,
            destination_stop_id="s",
            profile="wheelchair",
        )
    )
    assert response["extra_distance_m"] == 14
    assert response["standard"]["distance_m"] == 12
    assert response["alternative"]["distance_m"] == 26
    assert response["assumptions"]["profile_speed_mps"] == 0.9
    assert not response["alternative"]["mapped_stair_segments"]


def test_unavailable_comparison_does_not_invent_detour(study):
    study.remove_edge(1, 3)
    result = main.mobility_comparison(
        RouteComparisonRequest(
            origin_latitude=37.3296, origin_longitude=-121.903, destination_stop_id="s"
        )
    )
    assert result["alternative"] is None
    assert result["extra_distance_m"] is None
    assert result["unavailable_reason"]


def test_stop_and_letter_expose_unknown_boarding_and_model_limits(study):
    assert main.stop_detail("s")["wheelchair_boarding"] == 0
    assert main.stop_detail("s")["service"] is None
    assert main.stop_access("s")["standard"]["walkshed_polygon"]
    letter = main.civic_letter("s")
    assert "Fixture Stop" in letter and "not an on-site inspection" in letter
    assert "has not been sent" in letter
    with pytest.raises(HTTPException) as exc:
        main.stop_detail("absent")
    assert exc.value.status_code == 404


def test_ephemeral_production_report_is_rejected_before_writing(study, monkeypatch):
    from backend.app.observation_models import ObservationCreate

    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("TRANSITGAP_OBSERVATIONS_DB", raising=False)
    with pytest.raises(HTTPException) as exc:
        main.submit_observation(
            ObservationCreate(latitude=37.3296, longitude=-121.903, category="other"),
            None,
        )
    assert exc.value.status_code == 503
    assert main.health()["reports_enabled"] is False


def test_new_mcp_tools_share_synthetic_api_and_preserve_readonly_policy(study):
    async def run():
        async with Client(server, raise_exceptions=True) as client:
            for name, args in [
                ("worst_stops", {"limit": 1}),
                ("stop_access_report", {"stop_id": "s"}),
                ("stop_service", {"stop_id": "s"}),
                (
                    "compare_access",
                    {
                        "origin_latitude": 37.3296,
                        "origin_longitude": -121.903,
                        "destination_stop_id": "s",
                    },
                ),
            ]:
                result = await client.call_tool(name, args)
                assert not result.is_error, result
                assert result.structured_content

    anyio.run(run)
