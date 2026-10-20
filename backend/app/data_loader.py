from __future__ import annotations
import csv, io, os, zipfile
from math import hypot
from pathlib import Path
from typing import Any
import httpx
import networkx as nx
import osmnx as ox

CENTER = (37.3296, -121.9030)
DEFAULT_RADIUS_M = 1500
GTFS_URL = "https://gtfs.vta.org/gtfs_vta.zip"

class DatasetError(RuntimeError):
    pass

def data_dir() -> Path:
    # Vercel's deployment filesystem is read-only; /tmp is the only writable location.
    configured = os.getenv("TRANSITGAP_DATA_DIR")
    if configured:
        return Path(configured)
    if os.getenv("VERCEL"):
        packaged = Path(__file__).resolve().parents[1] / "data"
        if list(packaged.glob("walk-network-*.graphml")) and (packaged / "gtfs_vta.zip").exists():
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

def load_graph(radius_m: int = DEFAULT_RADIUS_M, directory: Path | None = None) -> nx.MultiDiGraph:
    directory = directory or data_dir()
    path = directory / f"walk-network-{radius_m}m.graphml"
    if path.exists():
        try:
            return ox.load_graphml(path)
        except Exception as exc:
            raise DatasetError(f"Cached OSM graph could not be read at {path}: {exc}") from exc
    try:
        # Extend OSMnx useful-tag allow-lists so source values survive import.
        ox.settings.useful_tags_way = list(dict.fromkeys([*ox.settings.useful_tags_way, "sidewalk", "kerb", "incline", "wheelchair", "smoothness", "footway", "steps"]))
        ox.settings.useful_tags_node = list(dict.fromkeys([*ox.settings.useful_tags_node, "sidewalk", "kerb", "incline", "wheelchair", "smoothness", "highway", "crossing", "barrier"]))
        graph = ox.graph_from_point(CENTER, dist=radius_m, network_type="walk", simplify=True, retain_all=True)
        # OSMnx supplies geodesic edge lengths and leaves absent source tags absent.
        directory.mkdir(parents=True, exist_ok=True)
        ox.save_graphml(graph, path)
        return graph
    except Exception as exc:
        raise DatasetError(f"Could not initialize the OpenStreetMap walking network: {exc}") from exc

def _nearest_graph_node(graph: nx.MultiDiGraph, latitude: float, longitude: float, nodes=None) -> Any:
    # The local region is small; a planar distance is sufficient for nearest-node selection.
    return min(nodes if nodes is not None else graph.nodes, key=lambda node: hypot((float(graph.nodes[node]["y"]) - latitude) * 111_320, (float(graph.nodes[node]["x"]) - longitude) * 88_500))

def load_stops(graph: nx.MultiDiGraph, radius_m: int = DEFAULT_RADIUS_M, directory: Path | None = None) -> list[dict[str, Any]]:
    directory = directory or data_dir()
    path = directory / "gtfs_vta.zip"
    if not path.exists():
        try:
            _download(GTFS_URL, path)
        except DatasetError as exc:
            raise DatasetError(f"{exc}. No previously cached official VTA feed is available.") from exc
    try:
        with zipfile.ZipFile(path) as archive:
            with archive.open("stops.txt") as source:
                reader = csv.DictReader(io.TextIOWrapper(source, encoding="utf-8-sig", newline=""))
                result = []
                connected = max(nx.weakly_connected_components(graph), key=len)
                for row in reader:
                    try:
                        lat, lon = float(row["stop_lat"]), float(row["stop_lon"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    if not (36.5 <= lat <= 38.0 and -122.5 <= lon <= -121.0):
                        continue
                    if hypot((lat - CENTER[0]) * 111_320, (lon - CENTER[1]) * 88_500) > radius_m:
                        continue
                    node = _nearest_graph_node(graph, lat, lon, connected)
                    n = graph.nodes[node]
                    # A transit stop must connect to the imported pedestrian graph nearby.
                    from math import radians, sin, cos, asin, sqrt
                    dlat, dlon = radians(float(n["y"])-lat), radians(float(n["x"])-lon)
                    a = sin(dlat/2)**2 + cos(radians(lat))*cos(radians(float(n["y"]))) * sin(dlon/2)**2
                    distance = 6371000 * 2 * asin(sqrt(a))
                    if distance > 150:
                        continue
                    result.append({"stop_id": row.get("stop_id", ""), "stop_name": row.get("stop_name", ""), "latitude": lat, "longitude": lon, "graph_node": str(node), "connector_distance_m": round(distance, 1)})
                if not result:
                    raise DatasetError("The official VTA feed loaded, but it contains no stops connected to this map region.")
                return result
    except DatasetError:
        raise
    except Exception as exc:
        raise DatasetError(f"Could not read stops.txt from the official VTA GTFS feed: {exc}") from exc

def initialize(radius_m: int | None = None) -> tuple[nx.MultiDiGraph, list[dict[str, Any]]]:
    radius = radius_m or int(os.getenv("TRANSITGAP_RADIUS_M", DEFAULT_RADIUS_M))
    graph = load_graph(radius)
    return graph, load_stops(graph, radius)
