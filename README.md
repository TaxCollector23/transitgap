# TransitGap

TransitGap is a Santa Clara County walking-to-transit planner. It connects a chosen starting point to real VTA stops using an OpenStreetMap walking network and official VTA GTFS stops. Route profiles can avoid mapped stairs or prefer paths with relevant documentation; neither profile certifies accessibility. Distances are shown in miles. County route coverage does not mean countywide sidewalk inspection coverage: municipal comparison currently uses a limited City of San José snapshot around Diridon Station. Other cities are not represented in that source.

## Local run

Requirements: Python 3.12 or newer and Node.js 20 or newer. The backend downloads and caches the walking graph and official VTA GTFS feed on first startup. The first run needs internet access and can take several minutes. The GraphML cache has a metadata manifest, and the filtered stop list is cached against the source file stats. If a download fails and no cache is available, the API reports an initialization error and does not invent data.

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 for the introduction or http://localhost:5173/app for the planner. API docs are at http://localhost:8000/docs. Without a prepared county graph, the local service falls back to the Diridon pilot area. To use a backend hosted elsewhere, set `VITE_API_URL` in the frontend build environment.

## GroundTruth

TransitGap GroundTruth compares the bounded San José Sidewalks polygon snapshot with explicitly mapped OSM pedestrian paths, and keeps official VTA stops as a separate source. Scroll to the **Sidewalk data gaps** panel to browse inspection candidates, view source provenance, toggle City sidewalk polygons, and submit a map-located community report. Reports are public, unverified, and do not change route calculations. The City polygons and priority list describe source data and information gaps; neither verifies sidewalk conditions or route accessibility.

The deployment build attempts to package a timestamped municipal snapshot. At runtime, the API uses the packaged snapshot or marks that source unavailable; it does not wait on the City service. Community reports use SQLite. Local filesystem storage persists locally; Vercel's default `/tmp` storage is instance-local and does not provide durable production reports. See [DATA_SOURCES.md](DATA_SOURCES.md), [ACCESSIBILITY_LIMITATIONS.md](ACCESSIBILITY_LIMITATIONS.md), and [TESTING.md](TESTING.md).

## MCP server

The API exposes nine read-only MCP tools over Streamable HTTP at `/mcp`. Tools use the same loaded route graph, VTA stops, and GroundTruth index as the REST API. Run `python scripts/smoke_mcp.py` after starting the backend to check the local endpoint; set `TRANSITGAP_MCP_URL` to check a deployed endpoint. The Render blueprint is in `render.yaml`. The server and hosted endpoint still require runtime verification. See [docs/MCP_SERVER.md](docs/MCP_SERVER.md).

## Run tests and build

```bash
cd backend && python -m pytest -q
cd ../frontend && npm run build
```

Run the real-browser desktop and mobile checks with the backend virtual environment from the local setup above:

```bash
cd frontend
npx playwright install chromium
npm run test:e2e
```

The Playwright report and failure traces are written to `frontend/test-artifacts/`; desktop and mobile screenshots are saved in `frontend/test-artifacts/screenshots/`.

Run the reproducible real-data benchmark (30 seeded GTFS pairs, five repeats per algorithm by default):

```bash
cd backend
python benchmarks/benchmark_routing.py --pairs 30 --repeats 5 --seed 7331
```

It writes every attempt to `backend/benchmarks/results.csv` and a median/p95 summary to `backend/benchmarks/summary.md`, including failed paths.

## API

- `GET /health` reports graph and GTFS readiness.
- `GET /coverage` reports the active route region. Deployment builds prepare the Santa Clara County OpenStreetMap walking graph and VTA stops; municipal sidewalk polygons currently come from the City of San Jose only.
- `GET /stops` returns official VTA stops that connect to the imported graph within 150 m.
- `POST /route` accepts origin latitude/longitude, a VTA stop ID, an algorithm (`dijkstra`, `bidirectional_dijkstra`, or `astar`) and profile (`standard`, `avoid_mapped_stairs`, or `prefer_documented_paths`). The response separates physical distance and weighted optimization cost and includes structured tag coverage.
- `POST /route/compare` runs all three profiles on the same origin, destination, and graph. Each profile returns its own route or an explicit unavailable result.

Route distances use the selected OSM edge lengths plus short connectors to the selected origin and transit stop. Geometry retains the selected parallel edge's way shape and direction. Durations assume 1.2 m/s. The API returns the assumption, the optimization cost separately, and a structured accessibility-data report. Missing tags remain unknown.

## Data, attribution, and limits

- OpenStreetMap © OpenStreetMap contributors, ODbL. Network data is fetched with OSMnx and cached locally as GraphML. The map uses the public OSM raster tile service with visible attribution. Keep tile traffic within the [OSM tile usage policy](https://operations.osmfoundation.org/policies/tiles/); for sustained production traffic, choose a tile provider with an explicit service agreement.
- VTA GTFS static feed: https://gtfs.vta.org/gtfs_vta.zip. The downloaded archive is cached locally and is excluded from Git.
- The graph is a walkable OSM network, not a complete sidewalk inventory. Roads in the OSM walk graph are not proof of a verified sidewalk. Missing accessibility tags do not mean a route is inaccessible or accessible. The stair-avoidance profile only excludes edges explicitly tagged as steps.
- Local caches are persistent. Vercel bundles the real graph and GTFS feed during its build so requests do not need to download them at cold start; each deployment has its own dataset snapshot.
- To refresh a local or deployment-build dataset intentionally, run `TRANSITGAP_REFRESH_DATA=true python scripts/prepare_deployment_data.py` from the repository root. Do not set that variable persistently for runtime traffic.
- TransitGap does not collect or store user location. Geolocation is requested only after the user selects “Use my location.”

## Engineering details

See [ENGINEERING.md](ENGINEERING.md) for algorithm and cost definitions, tag applicability, cache behavior, test fixture boundaries, benchmark interpretation, known limitations, and areas students can independently extend.
