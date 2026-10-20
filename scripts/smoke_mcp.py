"""Verify a deployed or locally running MCP endpoint with the official SDK client."""
from __future__ import annotations

import anyio
import os

from mcp import Client


EXPECTED_TOOLS = {
    "get_coverage", "search_transit_stops", "plan_route", "compare_routes",
    "analyze_route_accessibility", "find_accessibility_gaps", "get_gap_details",
    "get_inspection_priorities", "get_data_sources", "compare_access", "worst_stops", "stop_access_report", "stop_service",
}


async def main() -> None:
    endpoint = os.getenv("TRANSITGAP_MCP_URL", "http://127.0.0.1:8000/mcp")
    async with Client(endpoint) as client:
        tools = await client.list_tools()
        names = {tool.name for tool in tools.tools}
        if names != EXPECTED_TOOLS:
            raise SystemExit(f"Unexpected MCP tool set: {sorted(names)}")
        coverage = await client.call_tool("get_coverage", {})
        if coverage.is_error or not coverage.structured_content:
            raise SystemExit("get_coverage did not return structured coverage data")
        stops = await client.call_tool("search_transit_stops", {"query": "Diridon", "limit": 5})
        if stops.is_error or not stops.structured_content:
            raise SystemExit("search_transit_stops did not return structured stop data")
        print(f"Protocol: {client.protocol_version}")
        print(f"Server: {client.server_info.name if client.server_info else 'unknown'}")
        print(f"Region: {coverage.structured_content.get('region', 'not reported')}")
        print(f"Tools discovered: {len(names)}")
        print(f"Diridon search results: {stops.structured_content.get('count', 0)}")


if __name__ == "__main__":
    anyio.run(main)
