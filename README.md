# TransitGap

TransitGap finds walking routes from a chosen starting point to real VTA stops near San Jose Diridon Station. Phase 1 uses the OSM pedestrian network and official VTA GTFS stops. Route profiles can exclude edges explicitly mapped as stairs; this does not certify accessibility.

## Local run

Requirements: Python 3.12 or newer and Node.js 20 or newer. The backend downloads and caches the walking graph and the official VTA GTFS feed on first startup. The first run needs internet access and can take several minutes. If a download fails and no cache is available, the API reports an initialization error and does not invent data.

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

Open http://localhost:5173. API docs are at http://localhost:8000/docs. To use a backend hosted elsewhere, set `VITE_API_URL` in the frontend build environment.

## Run tests and build

```bash
cd backend && python -m pytest
cd ../frontend && npm run build
```

## API

- `GET /health` reports graph and GTFS readiness.
- `GET /coverage` describes the supported 1.5 km radius around Diridon Station.
- `GET /stops` returns official VTA stops that connect to the imported graph within 150 m.
- `POST /route` accepts origin latitude/longitude, a VTA stop ID, an algorithm (`dijkstra`, `bidirectional_dijkstra`, or `astar`) and profile (`standard` or `avoid_mapped_stairs`).

Route distances use OSM edge lengths plus short connectors to the selected origin and transit stop. Durations assume 1.2 m/s. The API returns the assumption and an accessibility warning. Missing tags remain unknown.

## Data, attribution, and limits

- OpenStreetMap © OpenStreetMap contributors, ODbL. Network data is fetched with OSMnx and cached locally as GraphML. The map uses the public OSM raster tile service with visible attribution. Keep tile traffic within the [OSM tile usage policy](https://operations.osmfoundation.org/policies/tiles/); for sustained production traffic, choose a tile provider with an explicit service agreement.
- VTA GTFS static feed: https://gtfs.vta.org/gtfs_vta.zip. The downloaded archive is cached locally and is excluded from Git.
- The graph is a walkable OSM network, not a complete sidewalk inventory. Missing accessibility tags do not mean a route is accessible. The stair-avoidance profile only excludes edges explicitly tagged as steps.
- Local caches are persistent. Vercel bundles the real graph and GTFS feed during its build so requests do not need to download them at cold start; each deployment has its own dataset snapshot.
- This Phase 1 does not collect or store user location. Geolocation is requested only after the user selects “Use my location.”

## Phase 2 candidates

Persist the OSM/GTFS datasets in a suitable backend host, refresh data on a schedule, add richer sidewalk and crossing constraints where mapped, and compare routing against field checks before making accessibility claims.
