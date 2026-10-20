# TransitGap

**[Open the site](https://transitgap.vercel.app/) · [Open the map](https://transitgap.vercel.app/app) · [Methods](docs/METHODOLOGY.md) · [Demo](DEMO.md)**

TransitGap measures the last part of a journey to public transit: how mobility preferences change a route, what accessibility information is missing, and which stops deserve closer examination.

It uses actual OpenStreetMap paths and official VTA GTFS across Santa Clara County. The current graph has 291,569 nodes, 811,314 directed edges and 3,348 connected VTA stops. City sidewalk comparisons remain a Diridon-area pilot. No route is independently certified accessible.

## What works

- Standard, wheelchair, stroller, low-vision and documented-path profiles, with visible unknowns and mapped concerns.
- A standard/profile mobility comparison with actual distance and time differences, stated speed assumptions and both routes on the map.
- A ten-minute network access study of 32 sampled stops, including partial edges, directionality and reciprocal-edge deduplication. Additional stops can be evaluated individually. Rankings apply only to evaluated stops.
- GTFS route joins, boarding status, service calendars and scheduled departures. These are not live arrivals.
- Directions from selected edge geometry, explicit address search, shareable journey links and editable civic letters.
- Five real graph algorithms under “Under the hood”: Dijkstra, bidirectional Dijkstra, A*, queue-based Bellman-Ford and breadth-first search. BFS minimizes segments, not walking distance.
- A scrolling landing page, a separate planner at `/app`, miles, loading states and mobile map controls. Evidence and the map renderer load separately from the core planner.
- A public read-only MCP server, plus a local stdio entrypoint.

## Local setup

Python 3.12 or newer and Node.js are required. Run backend commands from the repository root.

```sh
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -e . pytest
backend/.venv/bin/python scripts/prepare_deployment_data.py
backend/.venv/bin/python -m uvicorn backend.app.main:app --reload --port 8000
```

In another terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open the Vite URL. The default local API is `http://localhost:8000`. In production, the frontend uses the same origin. `VITE_API_URL` can override this at build time.

County preparation downloads a real Geofabrik Northern California extract when no graph cache is present. The source is large; preparation may take several minutes. Prepared graphs, filtered stops, compressed GTFS joins, sampled walksheds and the municipal evidence index are cached in `backend/data` and are not committed. A smaller study can use `TRANSITGAP_REGION=diridon` and `TRANSITGAP_RADIUS_M=1500`. No provider API key is required.

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Dataset, schedule and report-storage readiness; GTFS feed dates. |
| `GET /coverage` | Exact supported county polygon and source limitations. |
| `GET /stops` | Loaded VTA stops, coordinates and boarding status. |
| `GET /stops/{id}` | Routes and next three scheduled departures, with calendar awareness. |
| `POST /route` | Selected algorithm and mobility profile, ordered geometry, segment evidence and directions. |
| `POST /compare` | Standard versus selected-profile route and measured mobility detour. |
| `POST /route/compare` | All supported profile objectives, including the legacy alias. |
| `POST /algorithms/compare` | Per-request measurements for all five algorithms. |
| `GET /gaps?limit=10` | Ranked GeoJSON for evaluated stops; scope and assumptions included. |
| `GET /stops/{id}/access` | Two ten-minute reachable networks, display polygons and gap methodology. |
| `GET /letters/{id}` | Editable plain-text civic letter. Does not send a message. |
| `POST /geocode` | Explicit address search using `{ "query": "..." }`. |
| `GET /data-sources` | Provider availability and evidence provenance. |
| `GET /accessibility/gaps` | Municipal/OSM review candidates. |
| `GET /accessibility/gaps/{id}` | One evidence candidate. |
| `GET /accessibility/priorities` | Inspection suggestions from reproducibly sampled routes. |
| `GET /accessibility/municipal-sidewalks` | City sidewalk polygons within the pilot. |
| `GET, POST /accessibility/observations` | Unverified observations; writes require persistent local storage. |
| `POST /mcp` | Stateless Streamable HTTP MCP transport. |

Example route body:

```json
{
  "origin_latitude": 37.32875,
  "origin_longitude": -121.90442,
  "destination_stop_id": "4514",
  "algorithm": "astar",
  "profile": "wheelchair"
}
```

For `/compare`, supply the same origin, stop and profile. It uses A* for both routes so algorithm choice does not confound the comparison. `avoid_mapped_stairs` is retained as a wheelchair-profile alias for older clients.

## MCP

Remote URL: `https://transitgap.vercel.app/mcp`.

```sh
backend/.venv/bin/python -m mcp_server
TRANSITGAP_MCP_URL=https://transitgap.vercel.app/mcp backend/.venv/bin/python scripts/smoke_mcp.py
```

The 13 tools use the same backend functions as the web app. They expose coverage, stop search, routing, profile comparisons, evidence, inspection priorities, stop service and network access studies. There are no public write, shell, SQL, arbitrary URL-fetch or verification tools. See [client configuration](mcp_server/README.md).

## Verification and release

See [testing](TESTING.md), [current release status](docs/RELEASE_STATUS.md), [methods](docs/METHODOLOGY.md) and [accessibility limitations](ACCESSIBILITY_LIMITATIONS.md). Earlier Phase 4/5 audit files are historical snapshots; current release status takes precedence.

Deployment uses Vercel's FastAPI integration. Prepared data is bundled, static frontend files are promoted to the CDN, and `/app` rewrites to the same HTML shell. The backend remains available at its normal API paths. Test the public root, planner, API and MCP after every production release.

## Limits and privacy

Mapped tags are not field checks. Unknown conditions are not assumed accessible or inaccessible. Short off-network connectors, simplification and omitted source tags can affect results. Gap scores depend on both mapped conditions and assumed speeds; they are not infrastructure grades or population estimates.

Public report submission is paused on Vercel because `/tmp` storage is instance-local. Local SQLite remains available; a durable production store and review/retraction workflow are unfinished. Unreviewed reports never silently block routes.

Address text is sent to Nominatim only on explicit search. The proxy uses a bounded ten-minute memory cache and a per-process outbound throttle. Multi-instance scaling needs a shared rate coordinator or a separately hosted provider. Precise journey coordinates are shared only when a user chooses to create a journey URL.

Attribution: [© OpenStreetMap contributors](https://www.openstreetmap.org/copyright), [VTA GTFS](https://www.vta.org/go/developers), U.S. Census Bureau county boundary, Geofabrik extracts and City of San José sidewalk records. No field observations, testimonials or agency endorsements have been invented.
