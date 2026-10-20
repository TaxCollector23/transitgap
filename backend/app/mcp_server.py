"""Read-only TransitGap tools over MCP Streamable HTTP."""
from __future__ import annotations

import os
from typing import Any

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings


server = MCPServer("TransitGap")


def _api():
    # Import after main.py has finished defining the existing service functions.
    from . import main
    return main


@server.tool()
def get_coverage() -> dict[str, Any]:
    """Describe the supported walking-network area and its data limitations."""
    return _api().coverage()


@server.tool()
def search_transit_stops(query: str = "", limit: int = 10) -> dict[str, Any]:
    """Search loaded VTA stops by name; results include coordinates and stop IDs."""
    api = _api()
    api._ready()
    cleaned = query.strip().casefold()
    if len(cleaned) > 200 or not 1 <= limit <= 50:
        raise ValueError("query must be at most 200 characters and limit must be between 1 and 50")
    results = [
        {key: value for key, value in stop.items() if key not in {"graph_node", "connector_distance_m"}}
        for stop in api.state["stops"]
        if not cleaned or cleaned in stop["stop_name"].casefold()
    ][:limit]
    return {"query": query, "count": len(results), "stops": results}


@server.tool()
def plan_route(origin_latitude: float, origin_longitude: float, destination_stop_id: str,
               algorithm: str = "dijkstra", profile: str = "standard") -> dict[str, Any]:
    """Calculate a real walking route from a coordinate to a loaded VTA stop."""
    from .models import RouteRequest
    return _api().route(RouteRequest(
        origin_latitude=origin_latitude,
        origin_longitude=origin_longitude,
        destination_stop_id=destination_stop_id,
        algorithm=algorithm,
        profile=profile,
    ))


@server.tool()
def compare_routes(origin_latitude: float, origin_longitude: float,
                   destination_stop_id: str, algorithm: str = "astar") -> dict[str, Any]:
    """Compare supported walking profiles for the same origin and VTA stop."""
    from .models import RouteComparisonRequest
    return _api().compare_routes(RouteComparisonRequest(
        origin_latitude=origin_latitude,
        origin_longitude=origin_longitude,
        destination_stop_id=destination_stop_id,
        algorithm=algorithm,
    ))


@server.tool()
def analyze_route_accessibility(origin_latitude: float, origin_longitude: float,
                                destination_stop_id: str, algorithm: str = "astar",
                                profile: str = "standard") -> dict[str, Any]:
    """Return a route with its mapped accessibility tags and nearby source evidence."""
    from .models import RouteRequest
    result = _api().route(RouteRequest(
        origin_latitude=origin_latitude,
        origin_longitude=origin_longitude,
        destination_stop_id=destination_stop_id,
        algorithm=algorithm,
        profile=profile,
    ))
    return {
        "route": result,
        "interpretation": result.get("accessibility_warning"),
        "evidence": result.get("groundtruth_evidence"),
    }


@server.tool()
def find_accessibility_gaps(limit: int = 100, offset: int = 0,
                            bbox: list[float] | None = None) -> dict[str, Any]:
    """List evidence-based review candidates; a candidate is not a confirmed barrier."""
    api = _api()
    if not 1 <= limit <= 500 or not 0 <= offset <= 100_000:
        raise ValueError("limit must be 1-500 and offset must be between 0 and 100000")
    west = south = east = north = None
    if bbox is not None:
        if len(bbox) != 4:
            raise ValueError("bbox must be [west, south, east, north]")
        west, south, east, north = bbox
    api._bbox(west, south, east, north)
    return api._groundtruth().get_gaps(west=west, south=south, east=east, north=north,
                                       limit=limit, offset=offset)


@server.tool()
def get_gap_details(candidate_id: str) -> dict[str, Any]:
    """Get source matches, unknown fields, and explanation for one review candidate."""
    if not candidate_id or len(candidate_id) > 200:
        raise ValueError("candidate_id must be between 1 and 200 characters")
    candidate = _api()._groundtruth().get_candidate(candidate_id)
    if candidate is None:
        raise ValueError("Accessibility candidate not found")
    return candidate


@server.tool()
def get_inspection_priorities(limit: int = 50, offset: int = 0) -> dict[str, Any]:
    """Rank places for human review using TransitGap's implemented priority score."""
    if not 1 <= limit <= 200 or not 0 <= offset <= 100_000:
        raise ValueError("limit must be 1-200 and offset must be between 0 and 100000")
    return _api()._groundtruth().get_priorities(limit=limit, offset=offset)


@server.tool()
def get_data_sources() -> dict[str, Any]:
    """Describe data providers, availability, timestamps, and known limitations."""
    return _api()._groundtruth().source_status()


def _csv_setting(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


_render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
_default_hosts = ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*",
                  "transitgap.vercel.app", "transitgap.vercel.app:*"]
if _render_hostname:
    _default_hosts.extend([_render_hostname, f"{_render_hostname}:*"])
security = TransportSecuritySettings(
    allowed_hosts=_csv_setting("MCP_ALLOWED_HOSTS", ",".join(_default_hosts)),
    allowed_origins=_csv_setting("MCP_ALLOWED_ORIGINS", "https://transitgap.vercel.app"),
)

# The stateless transport avoids in-memory session affinity on horizontally scaled hosts.
asgi_app = server.streamable_http_app(
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
    max_request_body_size=64 * 1024,
    transport_security=security,
)
