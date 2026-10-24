"""Additional regional rail GTFS feeds and stops for walking destinations."""
from __future__ import annotations

import csv
import io
import logging
import re
import zipfile
from pathlib import Path
from typing import Any

from shapely.geometry import Point

from .data_loader import CENTER, COUNTY_REGION, DEFAULT_RADIUS_M, DatasetError, _download, load_county_boundary
from .geospatial import distance_m, nearest_graph_node

logger = logging.getLogger(__name__)

MAX_CONNECTOR_M = 150.0

AGENCIES = {
    "caltrain": {
        "name": "Caltrain",
        "feed_url": "https://data.trilliumtransit.com/gtfs/caltrain-ca-us/caltrain-ca-us.zip",
        "developer_url": "https://www.caltrain.com/developer-resources",
        "schedule_url": "https://www.caltrain.com/schedules",
        "file": "gtfs_caltrain.zip",
    },
    "bart": {
        "name": "BART",
        "feed_url": "https://www.bart.gov/dev/schedules/google_transit.zip",
        "developer_url": "https://www.bart.gov/schedules/developers/gtfs",
        "schedule_url": "https://www.bart.gov/planner",
        "file": "gtfs_bart.zip",
    },
}

DIRECTION_WORDS = ("Northbound", "Southbound", "Eastbound", "Westbound")


def _int(value: Any) -> int:
    try:
        return int(str(value or "0").strip() or 0)
    except ValueError:
        return 0


def station_records(rows: list[dict[str, str]]) -> tuple[dict[str, dict[str, str]], dict[str, list[dict[str, str]]]]:
    """GTFS parent stations (location_type 1) and entrances (location_type 2) by parent id."""
    parents = {row["stop_id"]: row for row in rows if row.get("location_type", "").strip() == "1"}
    entrances: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        if row.get("location_type", "").strip() == "2" and row.get("parent_station"):
            entrances.setdefault(row["parent_station"], []).append(row)
    return parents, entrances


def inherited_boarding(row: dict[str, str], parents: dict[str, dict[str, str]]) -> int:
    """GTFS: a platform's empty/0 wheelchair_boarding inherits its parent station's value."""
    own = _int(row.get("wheelchair_boarding"))
    if own:
        return own
    parent = parents.get(row.get("parent_station", ""))
    return _int(parent.get("wheelchair_boarding")) if parent else 0


def platform_label(row: dict[str, str], parent: dict[str, str] | None = None) -> str | None:
    """Label a platform only from fields the feed actually publishes.

    A direction in the stop name ("Santa Clara Caltrain Northbound") names the
    platform. A platform code is used only when the stop has no name of its own
    (BART platforms repeat the station name). Otherwise the stop's own name,
    such as "San Jose Diridon (Bay 11)", is already specific."""
    name = row.get("stop_name", "").strip()
    for word in DIRECTION_WORDS:
        if re.search(rf"\b{word}\b", name, re.IGNORECASE):
            return f"{word} platform"
    code = row.get("platform_code", "").strip()
    parent_name = (parent or {}).get("stop_name", "").strip()
    if code and (not parent or name == parent_name):
        return f"Platform {code}"
    return None


def connected_entrances(graph, rows: list[dict[str, str]], prefix: str) -> list[dict[str, Any]]:
    """Recorded station entrances that are close enough to a mapped path to route to."""
    result = []
    for row in rows:
        try:
            latitude, longitude = float(row["stop_lat"]), float(row["stop_lon"])
            node, _ = nearest_graph_node(graph, latitude, longitude)
            data = graph.nodes[node]
            connector = distance_m((latitude, longitude), (float(data["y"]), float(data["x"])))
        except (KeyError, TypeError, ValueError):
            continue
        if connector > MAX_CONNECTOR_M:
            continue
        result.append({
            "entrance_id": f"{prefix}{row['stop_id']}",
            "name": row.get("stop_name", "").strip() or "Station entrance",
            "latitude": latitude,
            "longitude": longitude,
            "wheelchair_boarding": _int(row.get("wheelchair_boarding")),
            "graph_node": str(node),
            "connector_distance_m": round(connector, 1),
        })
    return result


def station_fields(row: dict[str, str], parents: dict[str, dict[str, str]],
                   entrances: dict[str, list[dict[str, str]]], graph, prefix: str) -> dict[str, Any]:
    parent_id = row.get("parent_station", "").strip()
    parent = parents.get(parent_id)
    description = row.get("stop_desc", "").strip()
    direction = next(
        (word for word in DIRECTION_WORDS if re.search(rf"\b{word}\b", description, re.IGNORECASE)),
        None,
    )
    fields: dict[str, Any] = {
        "station_id": f"{prefix}{parent_id}" if parent else None,
        "station_name": parent.get("stop_name", "").strip() if parent else None,
        "platform_name": platform_label(row, parent) if parent else None,
        "station_url": (parent.get("stop_url") or "").strip() or None if parent else None,
        # Keep the agency-published stop description and any explicit travel
        # direction. These make similarly named boarding locations distinct.
        "direction": direction,
        "stop_description": description or None,
        "stop_code": row.get("stop_code", "").strip() or None,
    }
    if parent:
        fields["entrances"] = connected_entrances(graph, entrances.get(parent_id, []), prefix)
    return fields


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

        parents, entrances = station_records(feed_stops)
        prefix = f"{agency_id}:"
        loaded = 0
        for row in feed_stops:
            # Keep only boarding platforms. Parent stations and entrance records
            # describe them and are attached below rather than offered as stops.
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
            if connector > MAX_CONNECTOR_M:
                logger.info("Skipping %s platform %s: nearest mapped path is %.1fm away", config["name"], source_id, connector)
                continue
            stops.append({
                "stop_id": f"{prefix}{source_id}",
                "source_stop_id": source_id,
                "stop_name": name,
                "agency": agency_id,
                "agency_name": config["name"],
                "latitude": latitude,
                "longitude": longitude,
                "graph_node": str(node),
                "connector_distance_m": round(connector, 1),
                "wheelchair_boarding": inherited_boarding(row, parents),
                "schedule_type": "scheduled, not real-time",
                **station_fields(row, parents, entrances, graph, prefix),
            })
            loaded += 1
        if not loaded:
            if region == COUNTY_REGION:
                raise DatasetError(f"No {config['name']} platforms connect to the supported walking area.")
            logger.info("No %s platforms inside the %s m study area", config["name"], radius_m)
            continue
        metadata[agency_id] = {
            "name": config["name"],
            "feed_url": config["feed_url"],
            "developer_url": config["developer_url"],
            "schedule_url": config["schedule_url"],
            "feed_info": feed_info,
            "stop_count": loaded,
            "schedule_type": "scheduled, not real-time",
        }
    return stops, metadata
