"""Fetch real OSM and transit-agency data into the bundle before deployment."""
import os
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
os.environ["TRANSITGAP_DATA_DIR"] = str(root / "backend" / "data")
os.environ["TRANSITGAP_PREPARING_DATA"] = "1"
os.environ.setdefault("TRANSITGAP_REGION", "santa_clara_county")
os.environ.setdefault("TRANSITGAP_OVERPASS_URL", "https://overpass.private.coffee/api")
import osmnx as ox
ox.settings.log_console = True
from backend.app.data_loader import (COUNTY_RADIUS_M, COUNTY_REGION, DEFAULT_RADIUS_M, initialize,
                                    _download, _refresh_requested, _write_metadata, write_compact_graph)
from backend.app.data_sources.sanjose import load_sidewalks
from backend.app.data_sources.osm_extract import NORCAL_URL

county_graph = root / "backend" / "data" / "walk-network-santa-clara-county.graphml"
if os.environ["TRANSITGAP_REGION"] == COUNTY_REGION and (not (county_graph.exists() or county_graph.with_suffix(".jsonl.gz").exists()) or _refresh_requested()) and not os.getenv("TRANSITGAP_OSM_PBF"):
    extract_path = Path(tempfile.gettempdir()) / "transitgap-norcal.osm.pbf"
    print("Downloading the official Geofabrik Northern California OSM extract…", flush=True)
    _download(NORCAL_URL, extract_path)
    os.environ["TRANSITGAP_OSM_PBF"] = str(extract_path)
    os.environ["TRANSITGAP_DISPOSABLE_PBF"] = "1"

print(f"Preparing {os.environ['TRANSITGAP_REGION']} walking paths and VTA stops…", flush=True)
graph, stops = initialize()
print(f"Prepared OSM graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges")
print(f"Prepared official VTA stops connected to the graph: {len(stops)}")
from backend.app.transit_agencies import AGENCIES, load_agency_stops
rail_stops, transit_sources = load_agency_stops(graph, root / "backend" / "data", os.environ["TRANSITGAP_REGION"], COUNTY_RADIUS_M if os.environ["TRANSITGAP_REGION"] == COUNTY_REGION else DEFAULT_RADIUS_M)
for agency_id, source in transit_sources.items():
    print(f"Prepared {source['name']} scheduled platforms connected to the graph: {source['stop_count']}")
import gzip, json
compact_path = county_graph.with_suffix(".jsonl.gz")
legacy_snapshot = False
if compact_path.exists():
    with gzip.open(compact_path, "rt") as snapshot:
        legacy_snapshot = json.loads(next(snapshot)).get("format") != "transitgap-graph/2"
if os.environ["TRANSITGAP_REGION"] == COUNTY_REGION and (county_graph.exists() or legacy_snapshot):
    compact = county_graph.with_suffix(".jsonl.gz")
    print("Packing a streaming JSON walking graph for deployment…", flush=True)
    write_compact_graph(graph, compact)
    _write_metadata(compact, COUNTY_RADIUS_M, graph, COUNTY_REGION)
    county_graph.unlink(missing_ok=True)
    print(f"Packed county graph: {compact.stat().st_size / 1_000_000:.1f} MB", flush=True)
sidewalks = load_sidewalks(radius_m=DEFAULT_RADIUS_M, directory=root / "backend" / "data")
print(f"Prepared City of San Jose sidewalk comparison snapshot: {len(sidewalks.get('features', []))} features ({sidewalks.get('metadata', {}).get('availability', 'unavailable')}); other county municipalities are not covered by this source")

from backend.app.transit import TransitSchedule
from backend.app.gaps import GapIndex
print("Preparing static GTFS schedule joins…", flush=True)
from backend.app.transit import modes
vta_schedule = TransitSchedule(root / "backend" / "data" / "gtfs_vta.zip", [s['stop_id'] for s in stops])
for stop in stops:
    stop["modes"] = modes(vta_schedule.route_types(stop["stop_id"]))
    stop["routes_served"] = vta_schedule.routes_served(stop["stop_id"])
for agency_id, config in AGENCIES.items():
    ids = [stop["source_stop_id"] for stop in rail_stops if stop["agency"] == agency_id]
    if ids:
        agency_schedule = TransitSchedule(root / "backend" / "data" / config["file"], ids,
                                          root / "backend" / "data" / f"schedule-{agency_id}-v2.json.gz")
        for stop in rail_stops:
            if stop["agency"] == agency_id:
                stop["modes"] = modes(agency_schedule.route_types(stop["source_stop_id"]))
                stop["routes_served"] = agency_schedule.routes_served(stop["source_stop_id"])
print("Preparing a spatial sample of 32 ten-minute stop access studies…", flush=True)
gaps = GapIndex(graph, stops, root / "backend" / "data")
gaps.prepare(32)
print(f"Prepared {len(gaps.cache)} network walksheds", flush=True)

from backend.app.groundtruth_cache import load_groundtruth
print("Preparing immutable municipal evidence index…", flush=True)
index = load_groundtruth(graph, stops, sidewalks, root / "backend" / "data", gaps.signature)
print(f"Prepared {len(index.gaps)} municipal review candidates", flush=True)
from backend.app.public_api_snapshots import write_public_api_snapshots
from backend.app.reachability import PILOT_RADIUS_M, build_reachability_index, pilot_gtfs_stops
pilot_stops = pilot_gtfs_stops(graph, root / "backend" / "data" / "gtfs_vta.zip")
pilot_index = build_reachability_index(graph, pilot_stops, {}, vta_schedule.feed_info)
reachability_stops = {
    "study_area": {"name": "Diridon Station pilot", "radius_m": PILOT_RADIUS_M},
    "stop_count": len(pilot_index.stops),
    "stops": pilot_index.stop_list(),
    "source": "Actual VTA GTFS stops in the 1,500 m Diridon view of the county walking graph; nearest-node matches are not field checked.",
}
write_public_api_snapshots(
    root / "backend" / "data",
    index,
    transit_sources,
    reachability_stops=reachability_stops,
)
print("Prepared cold-start-safe source, priority, and reachability-stop API snapshots", flush=True)
from backend.app.prepared_frontend import export_frontend
export_frontend(graph, stops, gaps, os.environ['TRANSITGAP_REGION'], root / 'frontend' / 'public', rail_stops, transit_sources)
print('Exported prepared stop and network-study snapshots for CDN delivery', flush=True)
