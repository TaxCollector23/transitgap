"""Additional regional rail GTFS feeds and stops for walking destinations."""
from __future__ import annotations

import csv
import io
import logging
import zipfile
from pathlib import Path
from typing import Any

from shapely.geometry import Point

from .data_loader import CENTER, COUNTY_REGION, DEFAULT_RADIUS_M, DatasetError, _download, load_county_boundary
from .geospatial import distance_m, nearest_graph_node

logger = logging.getLogger(__name__)

AGENCIES = {
    "caltrain": {
        "name": "Caltrain",
        "feed_url": "https://data.trilliumtransit.com/gtfs/caltrain-ca-us/caltrain-ca-us.zip",
        "developer_url": "https://www.caltrain.com/developer-resources",
        "file": "gtfs_caltrain.zip",
    },
    "bart": {
        "name": "BART",
        "feed_url": "https://www.bart.gov/dev/schedules/google_transit.zip",
        "developer_url": "https://www.bart.gov/schedules/developers/gtfs",
        "file": "gtfs_bart.zip",
    },
}


def load_agency_stops(
    graph, directory: Path, region: str = COUNTY_REGION, radius_m: int = DEFAULT_RADIUS_M
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load scheduled rail platforms that can connect to the walking graph."""
    boundary = load_county_boundary() if region == COUNTY_REGION else None
    stops: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {}
    for agency_id, config in AGENCIES.items():
        path = directory / config["file"]
        if not path.exists():
            _download(config["feed_url"], path)
        try:
            with zipfile.ZipFile(path) as archive:
                if "stops.txt" not in archive.namelist():
                    raise DatasetError(f"{config['name']} GTFS feed has no stops.txt")
                with archive.open("stops.txt") as source:
                    reader = csv.DictReader(io.TextIOWrapper(source, encoding="utf-8-sig", newline=""))
                    feed_stops = list(reader)
                feed_info = []
                if "feed_info.txt" in archive.namelist():
                    with archive.open("feed_info.txt") as source:
                        feed_info = list(csv.DictReader(io.TextIOWrapper(source, encoding="utf-8-sig", newline="")))
        except (OSError, zipfile.BadZipFile, KeyError, csv.Error) as exc:
            raise DatasetError(f"Could not read {config['name']} GTFS: {exc}") from exc

        loaded = 0
        for row in feed_stops:
            # Keep only boarding platforms. Parent stations and entrance records
            # duplicate them and often have no scheduled stop times of their own.
            if row.get("location_type", "0") not in ("", "0"):
                continue
            source_id = row.get("stop_id", "").strip()
            name = row.get("stop_name", "").strip()
            try:
                latitude, longitude = float(row["stop_lat"]), float(row["stop_lon"])
            except (KeyError, TypeError, ValueError):
                continue
            if not source_id or not name or not (36.5 <= latitude <= 38.0 and -122.5 <= longitude <= -121.0):
                continue
            if boundary is not None and not boundary.covers(Point(longitude, latitude)):
                continue
            if boundary is None and distance_m((latitude, longitude), CENTER) > radius_m:
                continue
            try:
                node, _ = nearest_graph_node(graph, latitude, longitude)
                graph_node = graph.nodes[node]
                connector = distance_m((latitude, longitude), (float(graph_node["y"]), float(graph_node["x"])))
            except (ValueError, KeyError, TypeError):
                continue
            if connector > 150:
                logger.info("Skipping %s platform %s: nearest mapped path is %.1fm away", config["name"], source_id, connector)
                continue
            stops.append({
                "stop_id": f"{agency_id}:{source_id}",
                "source_stop_id": source_id,
                "stop_name": name,
                "agency": agency_id,
                "agency_name": config["name"],
                "latitude": latitude,
                "longitude": longitude,
                "graph_node": str(node),
                "connector_distance_m": round(connector, 1),
                "wheelchair_boarding": int(row.get("wheelchair_boarding") or 0),
                "schedule_type": "scheduled, not real-time",
            })
            loaded += 1
        if not loaded:
            raise DatasetError(f"No {config['name']} platforms connect to the supported walking area.")
        metadata[agency_id] = {
            "name": config["name"],
            "feed_url": config["feed_url"],
            "developer_url": config["developer_url"],
            "feed_info": feed_info,
            "stop_count": loaded,
            "schedule_type": "scheduled, not real-time",
        }
    return stops, metadata
