import zipfile

import networkx as nx
from shapely.geometry import box

from backend.app import main
from backend.app.transit_agencies import AGENCIES, load_agency_stops


def _feed(path, stops):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "stops.txt",
            "stop_id,stop_name,stop_lat,stop_lon,location_type,wheelchair_boarding\n"
            + "\n".join(",".join(row) for row in stops)
            + "\n",
        )
        archive.writestr("feed_info.txt", "feed_version,feed_end_date\nfixture,20270101\n")


def test_only_county_boarding_platforms_are_exposed_as_agency_stops(tmp_path, monkeypatch):
    for agency_id, config in AGENCIES.items():
        _feed(tmp_path / config["file"], [
            [f"{agency_id}-platform", "Station Platform", "37.3296", "-121.903", "0", "1"],
            [f"{agency_id}-parent", "Parent Station", "37.3296", "-121.903", "1", "0"],
            [f"{agency_id}-entrance", "Station Entrance", "37.3296", "-121.903", "2", "0"],
            [f"{agency_id}-outside", "Outside County", "37.8", "-122.4", "0", "0"],
        ])
    monkeypatch.setattr("backend.app.transit_agencies.load_county_boundary", lambda: box(-122, 37, -121, 38))
    graph = nx.MultiDiGraph()
    graph.add_node("walk", x=-121.903, y=37.3296)

    stops, sources = load_agency_stops(graph, tmp_path)

    assert [stop["stop_id"] for stop in stops] == ["caltrain:caltrain-platform", "bart:bart-platform"]
    assert [stop["agency_name"] for stop in stops] == ["Caltrain", "BART"]
    assert all(stop["graph_node"] == "walk" for stop in stops)
    assert sources["bart"]["feed_info"][0]["feed_end_date"] == "20270101"


def test_agency_stop_lists_and_walk_routing_accept_namespace_ids(client, monkeypatch):
    platform = {
        "stop_id": "bart:BERY-1", "source_stop_id": "BERY-1",
        "stop_name": "Berryessa / North San Jose", "agency": "bart",
        "agency_name": "BART", "latitude": 37.3685, "longitude": -121.874,
        "graph_node": "s", "connector_distance_m": 3, "wheelchair_boarding": 1,
    }
    vta = {"stop_id": "synthetic-unit", "stop_name": "Synthetic unit test stop",
           "latitude": 37.3296, "longitude": -121.902, "graph_node": "s"}
    monkeypatch.setitem(main.state, "transit_stops", [vta, platform])
    monkeypatch.setitem(main.state, "agency_schedules", {})
    monkeypatch.setitem(main.state, "transit_sources", {"bart": {"name": "BART", "stop_count": 1}})
    monkeypatch.setattr(main, "calculate_route", lambda *args, **kwargs: {
        "destination": {"stop_id": platform["stop_id"], "stop_name": platform["stop_name"],
                        "agency_name": platform["agency_name"]},
        "geometry": {"type": "LineString", "coordinates": [[-121.903, 37.3296], [-121.874, 37.3685]]},
    })

    listing = client.get("/stops")
    assert listing.status_code == 200
    assert listing.json()["count"] == 2
    assert listing.json()["stops"][1]["agency_name"] == "BART"
    detail = client.get("/stops/bart%3ABERY-1")
    assert detail.status_code == 200
    assert detail.json()["agency"] == "BART"
    response = client.post("/route", json={
        "origin_latitude": 37.3296, "origin_longitude": -121.903,
        "destination_stop_id": "bart:BERY-1",
    })
    assert response.status_code == 200
    assert response.json()["destination"]["agency_name"] == "BART"
