"""Build a county walk graph from a real Geofabrik OSM PBF extract."""
from __future__ import annotations

import gc
import re
import tempfile
from pathlib import Path
from xml.sax.saxutils import quoteattr

import osmium
import osmnx as ox
from pyproj import Transformer
from shapely.ops import transform


NORCAL_URL = "https://download.geofabrik.de/north-america/us/california/norcal-latest.osm.pbf"


def graph_from_extract(path: Path, boundary, *, remove_source: bool = False):
    # Apply OSMnx's actual walk filter so the extract and Overpass paths use
    # the same highway/access policy. Reject unsupported syntax explicitly.
    network_filter = ox._overpass._get_network_filter("walk")
    expression = re.compile(r'\["([^"]+)"(?:(~|!~)"([^"]*)")?\]')
    matches = list(expression.finditer(network_filter))
    if "".join(match.group() for match in matches) != network_filter:
        raise ValueError("The installed OSMnx walk filter has unsupported syntax")
    rules = [(match[1], match[2], re.compile(match[3]) if match[2] else None) for match in matches]

    def walkable(tags):
        for key, operator, pattern in rules:
            if operator is None and key not in tags:
                return False
            if operator == "!~" and pattern.search(tags.get(key, "")):
                return False
            if operator == "~" and not pattern.search(tags.get(key, "")):
                return False
        return True

    to_meters = Transformer.from_crs(4326, 26910, always_xy=True)
    to_wgs84 = Transformer.from_crs(26910, 4326, always_xy=True)
    buffered = transform(to_wgs84.transform, transform(to_meters.transform, boundary).buffer(500))
    west, south, east, north = buffered.bounds
    # Keep only IDs in the county envelope. A full Northern California node
    # location index can exceed a small deployment worker's memory budget.
    envelope_nodes: set[int] = set()
    for node in osmium.FileProcessor(path, osmium.osm.NODE):
        if west <= node.lon <= east and south <= node.lat <= north:
            envelope_nodes.add(node.id)
    print(f"Located {len(envelope_nodes)} nodes in the county envelope", flush=True)
    node_ids: set[int] = set()
    ways: list[str] = []
    processor = (osmium.FileProcessor(path, osmium.osm.WAY)
                 .with_filter(osmium.filter.KeyFilter("highway")))
    for way in processor:
        tags = dict(way.tags)
        if not walkable(tags) or len(way.nodes) < 2:
            continue
        refs = [node.ref for node in way.nodes]
        if not any(ref in envelope_nodes for ref in refs):
            continue
        node_ids.update(refs)
        ways.append(f'<way id="{way.id}">' + "".join(f'<nd ref="{ref}"/>' for ref in refs)
                    + "".join(f'<tag k={quoteattr(key)} v={quoteattr(value)}/>' for key, value in tags.items()) + '</way>\n')
    del processor
    del envelope_nodes
    gc.collect()
    if not ways:
        raise ValueError("The OSM extract contains no walking ways intersecting Santa Clara County")
    print(f"Extracted {len(ways)} walking ways and {len(node_ids)} referenced nodes", flush=True)

    with tempfile.TemporaryDirectory(prefix="transitgap-osm-") as temporary:
        xml_path = Path(temporary) / "county.osm"
        with xml_path.open("w", encoding="utf-8") as output:
            output.write('<osm version="0.6" generator="TransitGap">\n')
            nodes = osmium.FileProcessor(path, osmium.osm.NODE).with_filter(osmium.filter.IdFilter(node_ids))
            for node in nodes:
                output.write(f'<node id="{node.id}" lat="{node.lat}" lon="{node.lon}">')
                output.write("".join(f'<tag k={quoteattr(key)} v={quoteattr(value)}/>' for key, value in node.tags))
                output.write('</node>\n')
            output.writelines(ways)
            output.write('</osm>')
        # The regional download is a disposable build input. Release its disk
        # space before OSMnx writes the larger uncompressed graph cache.
        if remove_source:
            path.unlink()
        graph = ox.graph_from_xml(xml_path, bidirectional=True, simplify=True, retain_all=True)
    graph = ox.truncate.truncate_graph_polygon(graph, boundary, truncate_by_edge=False)
    graph.graph.update(source="OpenStreetMap via Geofabrik Northern California", source_url=NORCAL_URL,
                       walk_filter=network_filter)
    return graph
