"""Export measured public data for CDN delivery without a Python cold start."""

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from shapely.geometry import mapping
from .data_loader import CENTER, COUNTY_REGION, load_county_boundary


def export_frontend(graph, stops, gaps, region: str, public: Path, additional_stops=None, transit_sources=None):
    public.mkdir(parents=True, exist_ok=True)
    if region == COUNTY_REGION:
        boundary = load_county_boundary()
        west, south, east, north = boundary.bounds
        coverage = {
            "region": "Santa Clara County",
            "center": {"latitude": 37.25, "longitude": -121.93},
            "radius_m": 60000,
            "bounds": {"west": west, "south": south, "east": east, "north": north},
            "boundary": mapping(boundary),
            "description": "OpenStreetMap walking paths within the U.S. Census Santa Clara County boundary. Municipal evidence covers the Diridon pilot only.",
        }
    else:
        coverage = {
            "region": "Diridon Station area",
            "center": {"latitude": CENTER[0], "longitude": CENTER[1]},
            "radius_m": 1500,
            "description": "Diridon pilot walking network.",
        }
    timestamp = datetime.now(timezone.utc).isoformat()
    bootstrap = {
        "coverage": coverage,
        "stops": [
            {
                k: v
                for k, v in stop.items()
                if k not in {"graph_node", "connector_distance_m"}
            }
            for stop in [*stops, *(additional_stops or [])]
        ],
        "transit_sources": transit_sources or {},
        "prepared_at": timestamp,
        "graph_nodes": graph.number_of_nodes(),
        "graph_edges": graph.number_of_edges(),
        "source": "Build-time snapshot of the OpenStreetMap graph and VTA, Caltrain, and BART public GTFS schedule feeds used by the routing API.",
    }
    (public / "bootstrap.json").write_text(json.dumps(bootstrap, separators=(",", ":")))
    summary = gaps.summary(10)
    summary["prepared_at"] = timestamp
    (public / "study-summary.json").write_text(
        json.dumps(summary, separators=(",", ":"))
    )
    directory = public / "studies"
    directory.mkdir(exist_ok=True)
    from .letters import generate_letter

    letters = public / "prepared-letters"
    letters.mkdir(exist_ok=True)
    for stop_id, item in gaps.cache.items():
        # Current GTFS identifiers are numeric. Reject path-bearing identifiers.
        if not stop_id or not all(c.isalnum() or c in "-_" for c in stop_id):
            continue
        payload = {**item, "prepared_at": timestamp}
        (directory / f"{stop_id}.json").write_text(
            json.dumps(payload, separators=(",", ":"))
        )
        (letters / f"{stop_id}.txt").write_text(generate_letter(item))
    return bootstrap
