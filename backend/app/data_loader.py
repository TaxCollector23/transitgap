from __future__ import annotations
import csv, gzip, io, json, logging, os, zipfile
import sys
import math
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
import httpx
import networkx as nx
class _LazyOSMnx:
    """Keep build-only pandas/geopandas dependencies out of compact-cache startup."""
    def __getattr__(self, name):
        import importlib
        module = importlib.import_module("osmnx")
        return getattr(module, name)

ox = _LazyOSMnx()
from shapely.geometry import Point, shape
from .geospatial import distance_m, nearest_graph_node

CENTER = (37.3296, -121.9030)
DEFAULT_RADIUS_M = 1500
COUNTY_REGION = "santa_clara_county"
COUNTY_RADIUS_M = 60_000
COUNTY_BOUNDARY_PATH = Path(__file__).resolve().parent / "data_sources" / "santa_clara_county.geojson"
GTFS_URL = "https://gtfs.vta.org/gtfs_vta.zip"
GRAPH_SCHEMA_VERSION = 3
# Bump when the filtered stop record changes (boarding-only, stations, entrances).
STOP_SCHEMA_VERSION = 2
logger = logging.getLogger(__name__)
_GRAPH_CACHE: dict[str, tuple[int, int, nx.MultiDiGraph]] = {}


@lru_cache(maxsize=1)
def load_county_boundary():
    """Load the packaged U.S. Census Bureau boundary for Santa Clara County."""
    try:
        data = json.loads(COUNTY_BOUNDARY_PATH.read_text(encoding="utf-8"))
        feature = data["features"][0]
        if feature.get("properties", {}).get("geoid") != "06085":
            raise ValueError("Boundary GEOID is not Santa Clara County (06085)")
        polygon = shape(feature["geometry"])
        if polygon.is_empty or not polygon.is_valid:
            raise ValueError("County boundary is empty or invalid")
        return polygon
    except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        raise DatasetError(f"The packaged Santa Clara County boundary is unavailable: {exc}") from exc

USEFUL_WAY_TAGS = (
    "highway", "footway", "sidewalk", "crossing", "kerb", "surface", "smoothness",
    "incline", "wheelchair", "tactile_paving", "barrier", "width", "access", "foot",
    "indoor", "lit", "crossing:signals", "traffic_signals:sound", "name",
)
USEFUL_NODE_TAGS = (
    "highway", "crossing", "kerb", "surface", "smoothness", "incline", "wheelchair",
    "tactile_paving", "barrier", "width", "access", "foot", "lit", "crossing:signals", "traffic_signals:sound",
)


def _refresh_requested() -> bool:
    return os.getenv("TRANSITGAP_REFRESH_DATA", "").strip().lower() in {"1", "true", "yes"}


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()

class DatasetError(RuntimeError):
    pass

def data_dir() -> Path:
    # Vercel's deployment filesystem is read-only; /tmp is the only writable location.
    configured = os.getenv("TRANSITGAP_DATA_DIR")
    if configured:
        return Path(configured)
    if os.getenv("VERCEL"):
        packaged = Path(__file__).resolve().parents[1] / "data"
        if (list(packaged.glob("walk-network-*.graphml")) or list(packaged.glob("walk-network-*.jsonl.gz"))) and (packaged / "gtfs_vta.zip").exists():
            return packaged
        return Path("/tmp/transitgap")
    return Path(__file__).resolve().parents[1] / "data"

def _download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with httpx.stream("GET", url, timeout=90, follow_redirects=True) as response:
            response.raise_for_status()
            temp = target.with_suffix(target.suffix + ".part")
            with temp.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
            temp.replace(target)
    except Exception as exc:
        raise DatasetError(f"Could not download {url}: {exc}") from exc

def _graph_metadata(path: Path, radius_m: int, graph: nx.MultiDiGraph, region: str = "diridon") -> dict[str, Any]:
    stat = path.stat()
    way_counts = {tag: 0 for tag in USEFUL_WAY_TAGS}
    node_counts = {tag: 0 for tag in USEFUL_NODE_TAGS}
    for _, _, attrs in graph.edges(data=True):
        for tag in way_counts:
            if tag in attrs:
                way_counts[tag] += 1
    for _, attrs in graph.nodes(data=True):
        for tag in node_counts:
            if tag in attrs:
                node_counts[tag] += 1
    return {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "source": graph.graph.get("source", "OpenStreetMap via OSMnx"),
        "source_url": graph.graph.get("source_url", ox.settings.overpass_url),
        "center": {"latitude": CENTER[0], "longitude": CENTER[1]},
        "radius_m": radius_m,
        "region": region,
        "network_type": "walk",
        "osmnx_version": ox.__version__,
        "graph_file": path.name,
        "graph_size_bytes": stat.st_size,
        "graph_modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "manifest_generated_at": _timestamp(),
        "configured_way_tag_allowlist": list(USEFUL_WAY_TAGS),
        "configured_node_tag_allowlist": list(USEFUL_NODE_TAGS),
        "observed_way_tag_counts": way_counts,
        "observed_node_tag_counts": node_counts,
        "tag_capture_note": "Observed counts describe stored graph attributes. Tags absent from an older cache may have been omitted at acquisition; they are not proof that the street has no such feature.",
        "limitation": "Pedestrian network and accessibility tags are OpenStreetMap data, not a complete or field-verified sidewalk inventory.",
    }


def _write_metadata(path: Path, radius_m: int, graph: nx.MultiDiGraph, region: str = "diridon") -> None:
    metadata_path = path.with_suffix(".metadata.json")
    temp = metadata_path.with_suffix(".metadata.json.part")
    temp.write_text(json.dumps(_graph_metadata(path, radius_m, graph, region), indent=2), encoding="utf-8")
    temp.replace(metadata_path)


def _configure_osmnx_tags() -> None:
    if endpoint := os.getenv("TRANSITGAP_OVERPASS_URL", "").strip():
        ox.settings.overpass_url = endpoint.rstrip("/")
    ox.settings.useful_tags_way = list(dict.fromkeys([*ox.settings.useful_tags_way, *USEFUL_WAY_TAGS]))
    ox.settings.useful_tags_node = list(dict.fromkeys([*ox.settings.useful_tags_node, *USEFUL_NODE_TAGS]))


def graph_cache_path(directory: Path, radius_m: int, region: str) -> Path:
    graphml = directory / ("walk-network-santa-clara-county.graphml" if region == COUNTY_REGION
                          else f"walk-network-{radius_m}m.graphml")
    compact = graphml.with_suffix(".jsonl.gz")
    return compact if not graphml.exists() and compact.exists() else graphml


def write_compact_graph(graph: nx.MultiDiGraph, path: Path) -> None:
    """Serialize plain JSON records; no pickle or executable cache content."""
    from .graph_snapshot import write_blocks
    return write_blocks(graph, path)


def _write_legacy_graph(graph: nx.MultiDiGraph, path: Path) -> None:
    """Legacy writer retained for migration/regression benchmarks only."""
    def encode(value):
        if hasattr(value, "wkt"):
            return value.wkt
        if hasattr(value, "item"):
            return value.item()
        return str(value)
    temporary = path.with_suffix(path.suffix + ".part")
    with gzip.open(temporary, "wt", encoding="utf-8", compresslevel=6) as output:
        def record(value):
            output.write(json.dumps(value, default=encode, separators=(",", ":")) + "\n")
        record({"format": "transitgap-graph/1", "attributes": graph.graph})
        for node, attributes in graph.nodes(data=True):
            record({"node": node, "attributes": attributes})
        for u, v, key, attributes in graph.edges(keys=True, data=True):
            record({"edge": [u, v, key], "attributes": attributes})
    temporary.replace(path)


def read_compact_graph(path: Path) -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    metric_scale = 1.0
    canonical_nodes = {}
    def share_strings(record):
        return {sys.intern(key): sys.intern(value) if isinstance(value, str) and len(value) <= 128 else value
                for key, value in record.items()}
    with gzip.open(path, "rb") as source:
        header = json.loads(next(source))
        if header.get("format") == "transitgap-graph/2":
            from .graph_snapshot import read_blocks
            return read_blocks(source, header)
        if header.get("format") != "transitgap-graph/1":
            raise DatasetError("Unsupported compact walking graph format")
        graph.graph.update(header["attributes"])
        for line in source:
            record = json.loads(line, object_hook=share_strings)
            if "node" in record:
                node = record["node"]
                canonical_nodes[node] = node
                graph.add_node(node, **record["attributes"])
            else:
                u, v, key = record["edge"]
                graph.add_edge(canonical_nodes[u], canonical_nodes[v], key=key, **record["attributes"])
                # Verify a lower bound while reading the immutable source snapshot.
                # Arbitrary input graphs do not receive this certification.
                try:
                    a, b = graph.nodes[u], graph.nodes[v]
                    chord = distance_m((float(a["y"]), float(a["x"])), (float(b["y"]), float(b["x"])))
                    length = float(record["attributes"]["length"])
                    if not math.isfinite(length) or length < 0:
                        metric_scale = 0.0
                    elif chord > 0:
                        metric_scale = min(metric_scale, length / chord)
                except (KeyError, ValueError, TypeError):
                    metric_scale = 0.0
    graph.graph["transitgap_heuristic_scale"] = max(0.0, metric_scale * (1 - 1e-12))
    return graph


def load_graph(radius_m: int = DEFAULT_RADIUS_M, directory: Path | None = None,
               region: str = "diridon") -> nx.MultiDiGraph:
    directory = directory or data_dir()
    directory.mkdir(parents=True, exist_ok=True)
    if region not in {"diridon", COUNTY_REGION}:
        raise DatasetError(f"Unsupported TransitGap coverage region: {region}")
    path = graph_cache_path(directory, radius_m, region)
    refresh = _refresh_requested()
    if path.exists() and not refresh:
        stat = path.stat()
        cached = _GRAPH_CACHE.get(str(path.resolve()))
        if cached and cached[:2] == (stat.st_size, stat.st_mtime_ns):
            return cached[2]
        try:
            graph = read_compact_graph(path) if path.name.endswith(".jsonl.gz") else ox.load_graphml(path)
            _GRAPH_CACHE[str(path.resolve())] = (stat.st_size, stat.st_mtime_ns, graph)
            metadata_path = path.with_suffix(".metadata.json")
            rewrite_metadata = True
            if metadata_path.exists():
                try:
                    previous = json.loads(metadata_path.read_text(encoding="utf-8"))
                    rewrite_metadata = (previous.get("schema_version") != GRAPH_SCHEMA_VERSION
                                        or previous.get("region", "diridon") != region
                                        or previous.get("radius_m") != radius_m
                                        or previous.get("graph_size_bytes") != stat.st_size
                                        or previous.get("graph_modified_at") != datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat())
                except (OSError, ValueError, TypeError):
                    rewrite_metadata = True
            if rewrite_metadata:
                try:
                    _write_metadata(path, radius_m, graph, region)
                except Exception as exc:
                    # Packaged Vercel data is read-only at runtime. The graph
                    # remains usable; its manifest was prepared at build time.
                    logger.info("Could not update read-only OSM cache metadata: %s", exc)
            return graph
        except Exception as exc:
            logger.warning("Cached OSM graph is unreadable; attempting one clean data refresh: %s", exc)
    if os.getenv("TRANSITGAP_CACHE_ONLY") == "1":
        raise DatasetError("Prepared OSM graph is missing or unreadable; rebuild the data artifact before starting this service.")
    try:
        _configure_osmnx_tags()
        if refresh:
            logger.info("Refreshing the cached OpenStreetMap walking graph for radius %s m", radius_m)
        if region == COUNTY_REGION and (extract := os.getenv("TRANSITGAP_OSM_PBF")):
            from .data_sources.osm_extract import graph_from_extract
            graph = graph_from_extract(Path(extract), load_county_boundary(),
                                       remove_source=os.getenv("TRANSITGAP_DISPOSABLE_PBF") == "1")
        elif region == COUNTY_REGION:
            graph = ox.graph_from_polygon(load_county_boundary(), network_type="walk", simplify=True, retain_all=True)
        else:
            graph = ox.graph_from_point(CENTER, dist=radius_m, network_type="walk", simplify=True, retain_all=True)
        # Write to a separate GraphML file and atomically replace the prior cache
        # only after Overpass and serialization both succeed.
        replacement = directory / f"walk-network-{radius_m}m.refresh.graphml"
        ox.save_graphml(graph, filepath=replacement)
        replacement.replace(path)
        try:
            _write_metadata(path, radius_m, graph, region)
        except Exception as exc:
            # The newly acquired graph is already complete and atomically in
            # place. Metadata is useful for auditability but is not required
            # to route, so a manifest write failure must not discard the data.
            logger.warning("Could not write OSM cache metadata: %s", exc)
        stat = path.stat()
        _GRAPH_CACHE[str(path.resolve())] = (stat.st_size, stat.st_mtime_ns, graph)
        return graph
    except Exception as exc:
        logger.exception("Could not initialize OpenStreetMap walking graph")
        raise DatasetError(f"Could not initialize the OpenStreetMap walking network: {exc}") from exc


def _distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    return distance_m(a, b)


def _nearest_graph_node(graph: nx.MultiDiGraph, latitude: float, longitude: float, nodes=None) -> Any:
    # Compare geodesic distances over all candidate components. Restricting this
    # to the largest component can attach a nearby stop to a distant path.
    node, _ = nearest_graph_node(graph, latitude, longitude, nodes)
    return node

def load_stops(graph: nx.MultiDiGraph, radius_m: int = DEFAULT_RADIUS_M,
               directory: Path | None = None, region: str = "diridon") -> list[dict[str, Any]]:
    directory = directory or data_dir()
    path = directory / "gtfs_vta.zip"
    if not path.exists() or _refresh_requested():
        try:
            _download(GTFS_URL, path)
        except DatasetError as exc:
            raise DatasetError(f"{exc}. No previously cached official VTA feed is available.") from exc
    cache_path = directory / (f"stops-v{GRAPH_SCHEMA_VERSION}.{STOP_SCHEMA_VERSION}-santa-clara-county.json" if region == COUNTY_REGION
                              else f"stops-v{GRAPH_SCHEMA_VERSION}.{STOP_SCHEMA_VERSION}-{radius_m}m.json")
    try:
        feed_stat = path.stat()
        graph_path = graph_cache_path(directory, radius_m, region)
        graph_stat = graph_path.stat() if graph_path.exists() else None
        cache_meta = {"feed_size": feed_stat.st_size, "feed_mtime_ns": feed_stat.st_mtime_ns,
                      "graph_size": graph_stat.st_size if graph_stat else None,
                      "graph_mtime_ns": graph_stat.st_mtime_ns if graph_stat else None,
                      "radius_m": radius_m, "region": region}
        if not _refresh_requested() and cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            cached_stops = cached.get("stops")
            valid_stops = isinstance(cached_stops, list) and all(
                isinstance(stop, dict) and {"stop_id", "stop_name", "latitude", "longitude", "graph_node"}.issubset(stop)
                for stop in cached_stops
            )
            if cached.get("metadata") == cache_meta and valid_stops:
                return _boarding_status(cached_stops, path)
    except (OSError, ValueError, TypeError):
        cache_meta = {}
    try:
        from .transit_agencies import inherited_boarding, station_fields, station_records
        with zipfile.ZipFile(path) as archive:
            with archive.open("stops.txt") as source:
                rows = list(csv.DictReader(io.TextIOWrapper(source, encoding="utf-8-sig", newline="")))
                parents, entrances = station_records(rows)
                result = []
                for row in rows:
                    # Parent stations, entrances and generic nodes are not boarding
                    # locations; offering them as stops duplicated stations.
                    if row.get("location_type", "").strip() not in ("", "0"):
                        continue
                    try:
                        lat, lon = float(row["stop_lat"]), float(row["stop_lon"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    if not (36.5 <= lat <= 38.0 and -122.5 <= lon <= -121.0):
                        continue
                    if region == COUNTY_REGION:
                        if not load_county_boundary().covers(Point(lon, lat)):
                            continue
                    elif _distance_m((lat, lon), CENTER) > radius_m:
                        continue
                    node = _nearest_graph_node(graph, lat, lon)
                    n = graph.nodes[node]
                    # A transit stop must connect to the imported pedestrian graph nearby.
                    distance = _distance_m((lat, lon), (float(n["y"]), float(n["x"])))
                    if distance > 150:
                        continue
                    result.append({"stop_id": row.get("stop_id", ""), "stop_name": row.get("stop_name", ""), "latitude": lat, "longitude": lon,
                                   "graph_node": str(node), "connector_distance_m": round(distance, 1),
                                   "agency": "vta", "agency_name": "VTA",
                                   "wheelchair_boarding": inherited_boarding(row, parents),
                                   **station_fields(row, parents, entrances, graph, "")})
                if not result:
                    raise DatasetError("The official VTA feed loaded, but it contains no stops connected to this map region.")
                if cache_meta:
                    try:
                        temp = cache_path.with_suffix(".json.part")
                        temp.write_text(json.dumps({"metadata": cache_meta, "stops": result}, separators=(",", ":")), encoding="utf-8")
                        temp.replace(cache_path)
                    except OSError as exc:
                        # A serverless deployment can read bundled GTFS but
                        # cannot write a stop cache beside the package.
                        logger.info("Could not persist filtered VTA stop cache: %s", exc)
                return result
    except DatasetError:
        raise
    except Exception as exc:
        raise DatasetError(f"Could not read stops.txt from the official VTA GTFS feed: {exc}") from exc

def _boarding_status(stops, path):
    from .transit_agencies import inherited_boarding, station_records
    with zipfile.ZipFile(path) as archive:
        with archive.open("stops.txt") as source:
            rows = list(csv.DictReader(io.TextIOWrapper(source, encoding="utf-8-sig")))
    parents, _ = station_records(rows)
    statuses = {r["stop_id"]: inherited_boarding(r, parents) for r in rows}
    for stop in stops:
        stop["wheelchair_boarding"] = statuses.get(stop["stop_id"], 0)
    return stops


def initialize(radius_m: int | None = None) -> tuple[nx.MultiDiGraph, list[dict[str, Any]]]:
    configured_region = os.getenv("TRANSITGAP_REGION", "").strip().lower()
    packaged_county_graph = graph_cache_path(data_dir(), COUNTY_RADIUS_M, COUNTY_REGION)
    region = configured_region or (COUNTY_REGION if packaged_county_graph.exists() else "diridon")
    default_radius = COUNTY_RADIUS_M if region == COUNTY_REGION else DEFAULT_RADIUS_M
    radius = radius_m if radius_m is not None else int(os.getenv("TRANSITGAP_RADIUS_M", default_radius))
    if radius <= 0:
        raise DatasetError("TRANSITGAP_RADIUS_M must be a positive number of meters.")
    graph = load_graph(radius, region=region)
    return graph, load_stops(graph, radius, region=region)
