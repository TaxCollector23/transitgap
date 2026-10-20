from backend.app import main
from backend.app.reachability import ReachabilityIndex
import networkx as nx


def test_reachability_api_lists_real_pilot_fixture_and_returns_geojson(client, monkeypatch):
    graph = nx.MultiDiGraph()
    graph.add_node(1, x=-121.903, y=37.3296)
    graph.add_node(2, x=-121.902, y=37.3296)
    graph.add_edge(1, 2, length=100, highway="footway", surface="concrete", width="1m",
                   geometry=[[-121.903, 37.3296], [-121.902, 37.3296]], osmid=42)
    stops = [{"stop_id": "pilot-stop", "stop_name": "Pilot stop", "latitude": 37.3296,
              "longitude": -121.902, "graph_node": "2", "connector_distance_m": 5}]
    index = ReachabilityIndex(graph, stops, {"source": "OSM", "graph_modified_at": None}, [])
    monkeypatch.setattr(main, "_reachability_study", lambda: index)

    listing = client.get("/accessibility/reachability/stops")
    assert listing.status_code == 200
    assert listing.json()["stops"][0]["stop_id"] == "pilot-stop"
    response = client.get("/accessibility/reachability/pilot-stop?profile=wheelchair")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "OK"
    assert payload["stop"]["stop_id"] == "pilot-stop"
    assert payload["documented"]["geometry"]["type"] == "FeatureCollection"
    assert payload["gtfs_source"]["url"].startswith("https://gtfs.vta.org/")


def test_reachability_api_bounds_profile_and_stop(client, monkeypatch):
    graph = nx.MultiDiGraph()
    graph.add_node(1, x=-121.903, y=37.3296)
    stop = {"stop_id": "pilot-stop", "stop_name": "Pilot stop", "latitude": 37.3296,
            "longitude": -121.903, "graph_node": "1", "connector_distance_m": 5}
    index = ReachabilityIndex(graph, [stop], {}, [])
    monkeypatch.setattr(main, "_reachability_study", lambda: index)

    assert client.get("/accessibility/reachability/missing-stop").status_code == 404
    assert client.get("/accessibility/reachability/pilot-stop?minutes=16").status_code == 422
    assert client.get("/accessibility/reachability/pilot-stop?profile=prefer_documented_paths").status_code == 422


def test_real_analysis_adapter_exposes_exact_source_linked_inspection_impact(client, monkeypatch):
    graph = nx.MultiDiGraph()
    graph.add_node('o', x=-121.903, y=37.3296)
    graph.add_node('s', x=-121.902, y=37.3296)
    graph.add_edge('o', 's', key=0, length=100, highway='footway', surface='concrete', osmid=42)
    stop = {'stop_id':'vta-test','stop_name':'Synthetic VTA API fixture','latitude':37.3296,
            'longitude':-121.902,'graph_node':'s','connector_distance_m':5}
    index=ReachabilityIndex(graph,[stop],{},[])
    monkeypatch.setattr(main,'_reachability_study',lambda:index)
    result=client.get('/accessibility/reachability/vta-test').json()
    impact=result['inspection_priorities']
    assert impact['metric']=='sampled_journey_reachability_sensitivity'
    candidate=impact['candidates'][0]
    assert candidate['score']==candidate['sample_count']==1
    assert candidate['source_url']=='https://www.openstreetmap.org/way/42'
    assert candidate['affected_pairs']==[['o','vta-test']]
    assert result['documented']['reachable_sample_origins']==0
    sensitivity=client.get('/accessibility/reachability/vta-test?documentation_policy=width_optional_sensitivity').json()
    assert sensitivity['documented']['reachable_sample_origins']==1
    assert client.get('/accessibility/reachability/vta-test?documentation_policy=anything').status_code==422
