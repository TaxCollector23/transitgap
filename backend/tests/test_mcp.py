from __future__ import annotations

import anyio
import pytest
from mcp import Client

from backend.app.mcp_server import server


def test_mcp_discovers_only_read_only_transitgap_tools():
    async def check():
        async with Client(server, raise_exceptions=True) as client:
            result = await client.list_tools()
            names = {tool.name for tool in result.tools}
            assert names == {
                "get_coverage", "search_transit_stops", "plan_route", "compare_routes",
                "analyze_route_accessibility", "find_accessibility_gaps", "get_gap_details",
                "get_inspection_priorities", "get_data_sources",
            }
            coverage = await client.call_tool("get_coverage", {})
            assert not coverage.is_error
            assert coverage.structured_content

    anyio.run(check)


@pytest.mark.integration
def test_slashless_http_mcp_endpoint_precedes_static_frontend(client):
    response = client.post("/mcp", headers={"Accept": "application/json, text/event-stream"}, json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                   "clientInfo": {"name": "transitgap-regression", "version": "1"}},
    })
    assert response.status_code == 200
    assert response.json()["result"]["serverInfo"]["name"] == "TransitGap"
