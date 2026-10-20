# TransitGap MCP

Remote Streamable HTTP: `https://transitgap.vercel.app/mcp`.

Local stdio: `backend/.venv/bin/python -m mcp_server` from the repository root. [Client configuration](../mcp_server/README.md).

## Read-only tools

`get_coverage`, `search_transit_stops`, `plan_route`, `compare_routes`, `analyze_route_accessibility`, `find_accessibility_gaps`, `get_gap_details`, `get_inspection_priorities`, `get_data_sources`, `compare_access`, `worst_stops`, `stop_access_report`, `stop_service`.

Tools import the same route, evidence, GTFS and network-study functions as the website. Results preserve unknown conditions, source provenance, model assumptions and warnings. `worst_stops` ranks only evaluated stops. `stop_service` returns scheduled data, never live arrivals.

The official MCP SDK provides stateless JSON Streamable HTTP and stdio. The exact slashless `/mcp` endpoint is registered before the frontend catch-all. Request bodies are bounded to 64 KB. Hosts/origins are allowlisted, input ranges are validated and route searches have a time budget. Unique Vercel preview hosts are not automatically trusted; test the stable public hostname.

No public write, admin verification, arbitrary URL, shell, SQL, file access or credential tools are exposed. Community report submission is intentionally not a public MCP tool.

## Verification

```sh
backend/.venv/bin/python -m pytest backend/tests/test_mcp.py backend/tests/test_product_api.py -q
TRANSITGAP_MCP_URL=https://transitgap.vercel.app/mcp backend/.venv/bin/python scripts/smoke_mcp.py
```

See the release report for final deployed-client smoke results. The earlier Render blueprint is optional hosting configuration, not a claim that a Render service was created.
