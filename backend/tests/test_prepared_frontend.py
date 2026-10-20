import json
import networkx as nx
from backend.app.gaps import GapIndex
from backend.app.prepared_frontend import export_frontend


def test_cdn_snapshots_match_measured_data_and_exclude_internal_connections(tmp_path):
    graph = nx.MultiDiGraph()
    graph.add_node(1, x=-121.903, y=37.3296)
    graph.add_node(2, x=-121.903, y=37.3297)
    graph.add_edge(1, 2, length=12, highway="footway")
    stops = [
        {
            "stop_id": "s",
            "stop_name": "Fixture stop",
            "latitude": 37.3297,
            "longitude": -121.903,
            "graph_node": 2,
            "connector_distance_m": 0,
            "wheelchair_boarding": 0,
        }
    ]
    gaps = GapIndex(graph, stops, tmp_path)
    gaps.prepare(1)
    public = tmp_path / "public"
    export_frontend(graph, stops, gaps, "diridon", public)
    bootstrap = json.loads((public / "bootstrap.json").read_text())
    assert bootstrap["stops"][0]["stop_id"] == "s"
    assert "graph_node" not in bootstrap["stops"][0]
    assert bootstrap["graph_nodes"] == 2
    assert (
        json.loads((public / "study-summary.json").read_text())["evaluated_stop_count"]
        == 1
    )
    assert (
        json.loads((public / "studies/s.json").read_text())["standard"][
            "reachable_length_m"
        ]
        == 12
    )
    letter = (public / "prepared-letters/s.txt").read_text()
    assert "Fixture stop" in letter and "has not been sent" in letter
