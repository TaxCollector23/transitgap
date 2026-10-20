import osmium
from shapely.geometry import box
from backend.app.data_loader import _configure_osmnx_tags
from backend.app.data_sources.osm_extract import graph_from_extract


def test_pbf_walk_filter_preserves_tags_and_excludes_private_ways(tmp_path):
    path = tmp_path / "fixture.osm.pbf"
    with osmium.SimpleWriter(str(path)) as writer:
        for node, longitude in [(1, -121.9), (2, -121.899), (3, -121.898)]:
            writer.add_node(osmium.osm.mutable.Node(id=node, location=(longitude, 37.3),
                            tags={"highway": "crossing"} if node == 1 else {}))
        writer.add_way(osmium.osm.mutable.Way(id=100, nodes=[1, 2],
                       tags={"highway": "footway", "name": "A & B", "wheelchair": "yes"}))
        writer.add_way(osmium.osm.mutable.Way(id=101, nodes=[2, 3],
                       tags={"highway": "footway", "access": "private"}))
    _configure_osmnx_tags()
    graph = graph_from_extract(path, box(-121.91, 37.29, -121.89, 37.31))
    assert set(graph.nodes) == {1, 2}
    assert graph.nodes[1]["highway"] == "crossing"
    assert graph[1][2][0]["name"] == "A & B"
    assert graph[1][2][0]["wheelchair"] == "yes"
    assert path.exists()
