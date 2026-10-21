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


def _station_feed(path, feed_info="feed_version,feed_end_date\nfixture,20270101\n"):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "stops.txt",
            "stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station,platform_code,wheelchair_boarding,stop_url\n"
            "P1,Test Caltrain Northbound,37.3296,-121.903,0,PARENT,,,\n"
            "P2,Test Station,37.3296,-121.903,0,PARENT,2,2,\n"
            "PARENT,Test Station,37.3296,-121.903,1,,,1,https://example.org/station\n"
            "E1,Main Entrance,37.3297,-121.903,2,PARENT,,1,\n"
            "E2,Far Entrance,37.40,-121.903,2,PARENT,,0,\n",
        )
        archive.writestr("feed_info.txt", feed_info)


def test_platforms_inherit_station_boarding_and_link_entrances(tmp_path, monkeypatch):
    for config in AGENCIES.values():
        _station_feed(tmp_path / config["file"])
    monkeypatch.setattr("backend.app.transit_agencies.load_county_boundary", lambda: box(-122, 37, -121, 38))
    graph = nx.MultiDiGraph()
    graph.add_node("walk", x=-121.903, y=37.3296)
    stops, _ = load_agency_stops(graph, tmp_path)
    caltrain = [s for s in stops if s["agency"] == "caltrain"]
    northbound, second = caltrain
    # GTFS: an empty platform value inherits the parent; an explicit value wins.
    assert northbound["wheelchair_boarding"] == 1
    assert second["wheelchair_boarding"] == 2
    assert northbound["platform_name"] == "Northbound platform"
    assert second["platform_name"] == "Platform 2"
    assert northbound["station_id"] == "caltrain:PARENT" and northbound["station_name"] == "Test Station"
    assert northbound["station_url"] == "https://example.org/station"
    # The far entrance is not within reach of a mapped path, so it is not routable.
    assert [e["name"] for e in northbound["entrances"]] == ["Main Entrance"]


def test_step_free_profiles_only_route_to_recorded_accessible_entrances():
    from backend.app.models import Profile
    stop = {"stop_id": "x", "stop_name": "Platform", "station_name": "Station", "graph_node": "p",
            "latitude": 1, "longitude": 1, "entrances": [
                {"entrance_id": "a", "name": "Stairs only", "wheelchair_boarding": 2, "graph_node": "a", "latitude": 1, "longitude": 1},
                {"entrance_id": "b", "name": "Elevator", "wheelchair_boarding": 1, "graph_node": "b", "latitude": 1, "longitude": 1},
                {"entrance_id": "c", "name": "Unrecorded", "wheelchair_boarding": 0, "graph_node": "c", "latitude": 1, "longitude": 1},
            ]}
    names = lambda profile: [t[2]["name"] for t in main._arrival_targets(stop, profile)]
    assert names(Profile.standard) == ["Stairs only", "Elevator", "Unrecorded"]
    assert names(Profile.wheelchair) == ["Elevator"]
    no_recorded = {**stop, "entrances": [e for e in stop["entrances"] if e["entrance_id"] != "b"]}
    assert [t[2]["name"] for t in main._arrival_targets(no_recorded, Profile.stroller)] == ["Unrecorded"]
    assert main._arrival_targets({**stop, "entrances": []}, Profile.wheelchair)[0][2]["type"] == "stop"


def test_schedules_outside_their_published_period_are_never_current(tmp_path):
    from datetime import datetime
    from backend.app.transit import TIMEZONE, TransitSchedule
    archive = tmp_path / "feed.zip"
    with zipfile.ZipFile(archive, "w") as feed:
        feed.writestr("feed_info.txt", "feed_publisher_name,feed_start_date,feed_end_date\nX,20261026,20270110\n")
        feed.writestr("routes.txt", "route_id,route_short_name,route_long_name,route_type\nR,22,Test,3\n")
        feed.writestr("trips.txt", "route_id,service_id,trip_id,trip_headsign\nR,S,T,Downtown\n")
        feed.writestr("calendar.txt", "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\nS,1,1,1,1,1,1,1,20260101,20271231\n")
        feed.writestr("stop_times.txt", "trip_id,stop_id,departure_time\nT,A,12:00:00\n")
    schedule = TransitSchedule(archive, ["A"], tmp_path / "cache.json.gz")
    before = schedule.details("A", datetime(2026, 10, 20, 8, tzinfo=TIMEZONE))
    assert before["schedule_validity"]["status"] == "not_yet_valid"
    assert before["scheduled_departures"] == [] and "starts 10/26/2026" in before["message"]
    assert before["routes"][0]["route_short_name"] == "22"
    during = schedule.details("A", datetime(2026, 11, 2, 8, tzinfo=TIMEZONE))
    assert during["schedule_validity"]["status"] == "current" and len(during["scheduled_departures"]) == 1
    after = schedule.details("A", datetime(2027, 2, 1, 8, tzinfo=TIMEZONE))
    assert after["schedule_validity"]["status"] == "expired" and after["scheduled_departures"] == []
    assert schedule.route_types("A") == ["3"]
