# TransitGap MCP server

TransitGap exposes a read-only Model Context Protocol server over Streamable HTTP at `/mcp`. It uses the same initialized graph, VTA GTFS stops, route functions, and GroundTruth evidence as the REST API. Tools do not add reports, change route data, or label a location accessible.

## Tools

| Tool | Purpose |
|---|---|
| `get_coverage` | Return the active supported region and limitations. |
| `search_transit_stops` | Search loaded VTA stops by name. |
| `plan_route` | Plan a walk to a selected VTA stop. |
| `compare_routes` | Compare the supported route profiles. |
| `analyze_route_accessibility` | Return route tags and nearby evidence with caveats. |
| `find_accessibility_gaps` | List source-data review candidates, optionally by bounding box. |
| `get_gap_details` | Return source matches and unknown fields for a candidate. |
| `get_inspection_priorities` | Return the implemented ranking for human review. |
| `get_data_sources` | Return source availability and known limits. |

The county map/route graph and VTA stop search may cover Santa Clara County when the county dataset is configured. Municipal sidewalk evidence remains limited to a City of San José pilot snapshot near Diridon Station. Countywide route coverage does not imply countywide inspection evidence.

## Run and check

Install the project dependencies, start the FastAPI service, and run:

```sh
python scripts/smoke_mcp.py
```

For a hosted endpoint:

```sh
TRANSITGAP_MCP_URL=https://<actual-host>/mcp python scripts/smoke_mcp.py
```

The Render blueprint is `render.yaml`. Set `MCP_ALLOWED_HOSTS` to the actual service hostname and `MCP_ALLOWED_ORIGINS` to intended browser origins. The checked-in Render hostname is a proposed name and must be verified after service creation. An in-process test is in `backend/tests/test_mcp.py`; it does not replace the HTTP smoke check. Neither has been run for this release.
