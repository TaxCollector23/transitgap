# Phase 5 baseline and implementation notes

## Repository baseline

- Frontend: React 19, TypeScript, Vite, MapLibre GL, and Playwright.
- Backend: FastAPI, OSMnx, NetworkX, Shapely, and the official VTA GTFS stops feed.
- Route computation uses the existing pedestrian graph and Dijkstra, bidirectional Dijkstra, and A* implementations.
- Public API includes route comparison, accessibility evidence, data sources, priorities, and community observations.
- Vercel configuration was a minimal project manifest. No Render service or production MCP endpoint was present in the repository.
- Community observations use SQLite. Vercel and a free Render instance do not provide durable local storage.

## Phase 5 changes in this checkout

- `/` is an editorial introduction and `/app` serves the route planner. The FastAPI static deployment has an `/app` history fallback.
- The app presents route inputs as A (a map coordinate) and B (a real VTA stop). Map selection modes are exclusive and cancellable. Report placement is R and clears after a successful report.
- Route and stop distances, speed assumptions, and evidence distances are shown in miles.
- The map displays an initialization loader, selection instructions, and a map key.
- The county build path prepares an OSM walking graph and VTA stops for the U.S. Census Santa Clara County boundary. Municipal sidewalk comparison remains a 1,500 m Diridon pilot snapshot from the City of San Jose. OSM and VTA coverage therefore does not imply countywide municipal inspection evidence.
- A read-only MCP Streamable HTTP server exposes nine tools backed by the current TransitGap service functions. It is mounted at `/mcp` and has a Render blueprint and SDK smoke client.
- The map, county graph build, MCP HTTP protocol, deployment, and persistence changes have not passed runtime verification in this environment.

## Verification recorded

- TypeScript compiler API check: frontend source files passed with zero diagnostics after the UI changes.
- Full frontend production build: not verified. A prior Vite API build attempt failed because the installed dependency tree lacked Rollup's optional macOS binary.
- Manual built-in browser checks passed for the landing/planner link, direct planner refresh, A/B selection, stop search, mile display, warning units, mobile sheet behavior, report-mode cancellation, and reset. See [BROWSER_QA.md](BROWSER_QA.md). The running local backend is still the earlier Diridon version, so this does not validate the new backend.
- Backend tests, the automated browser E2E suite, accessibility scan, county graph acquisition, MCP client over HTTP, and new deployment health checks: not run.
- Terminal commands are currently blocked before execution by the local pre-tool hook: `Trace could not check this action: fetch failed`. Git state and remote deployment status could not be inspected safely.

The release is **not ready** until the open items in [PHASE5_ISSUES.md](PHASE5_ISSUES.md) are resolved and verified.
