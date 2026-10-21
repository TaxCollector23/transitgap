# Verification

Run from the repository root unless stated otherwise:

```sh
backend/.venv/bin/python -m pytest backend/tests -q --disable-warnings
backend/.venv/bin/python -m pytest backend/tests -m 'not integration' -q --disable-warnings
npm --prefix frontend run build
npm --prefix frontend run test:e2e
git diff --check
```

Integration tests need prepared real OSM/VTA datasets. Offline unit tests use synthetic graphs and GTFS fixtures. Playwright starts or reuses the local API and Vite server. Install Chromium with `cd frontend && npx playwright install chromium` when necessary.

The suite covers directed and parallel edges, profile costs, exclusions, unknown tags, geometry continuity, connectors, detour availability, GTFS calendars and overnight service, partial walkshed edges, reciprocal geometry, source-cache invalidation, PII normalization, read-only MCP and ephemeral report rejection. A 5,000-node route has a two-second request budget.

Browser checks (`frontend/e2e/transitgap.spec.ts`) follow first-time-user tasks against the real county data: the primary task is obvious on open; finding a stop by name and agency; choosing an origin without the map; VTA, Caltrain and BART journeys with a profile change that must recalculate; grouped directions with no "unnamed" or per-step "Information missing" text and distances that sum to the route; the missing-data summary; access gaps and reporting one step away and back without losing the route; the whole flow by keyboard; a simulated backend outage; mobile (390×844) journeys for all three agencies including full-screen directions; all five profiles and five algorithms; and trip links. Each journey runs an axe WCAG 2.2 AA scan. Screenshots go to `frontend/test-artifacts/screenshots`. Automated checks do not replace keyboard, screen-reader or real-world user evaluation; see `docs/USABILITY_TEST.md` for the unassisted participant protocol.

Maneuver grouping is covered by synthetic graphs in `backend/tests/test_directions.py`: continuous unnamed footways, named streets, borrowed-name prevention, genuine junctions versus forced bends, curving roads, very short segments, repeated OSM ways and parallel edges, straight and turning crossings, clustered crossing nodes, stairs and the wheelchair detour around them, unmapped connectors, and route-level missing-data summaries.

A production-preview regression blocks live data endpoints and still opens the prepared stop selector, network study and editable letter. Build the frontend before running Playwright so its preview server has the actual generated snapshots.

MCP verification:

```sh
TRANSITGAP_MCP_URL=http://127.0.0.1:8000/mcp backend/.venv/bin/python scripts/smoke_mcp.py
TRANSITGAP_MCP_URL=https://transitgap.vercel.app/mcp backend/.venv/bin/python scripts/smoke_mcp.py
```

The official SDK also exercises the in-memory server in pytest. The local `python -m mcp_server` stdio transport was tested with the official SDK client and discovered 13 tools.

See `docs/RELEASE_STATUS.md` for actual run results and release gaps. Test reports, screenshots, videos and traces are generated under `frontend/test-artifacts` and are not committed. Public browser checks must not create fabricated community reports.
