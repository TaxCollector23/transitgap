# Test matrix

“Added” means a test exists in the repository. It does not mean the test passed.

Manual checks in the built-in browser are recorded in [BROWSER_QA.md](BROWSER_QA.md). Those checks covered the current frontend against the already running Diridon route service. Automated suite statuses below remain unchanged until the commands can run.

| Component | Critical workflow | Test or evidence | Current status | Remaining work |
|---|---|---|---|---|
| Landing page | Open `/`, follow CTA to `/app`, refresh planner URL | `frontend/e2e/transitgap.spec.ts` | Added; not run | Browser check on desktop and mobile |
| Route input selection | Set A on map, select B VTA stop, cancel and reset | `frontend/e2e/transitgap.spec.ts` | Regression coverage added; not run | Confirm live map click precedence and geofence |
| Stop search | Search and select a real VTA stop | `frontend/e2e/transitgap.spec.ts` | Existing; not run | Run against prepared county GTFS graph |
| Route algorithms and profiles | Calculate using supported algorithms and profiles | `backend/tests/test_routing.py`, `frontend/e2e/transitgap.spec.ts` | Present; not run this turn | Full county performance and route correctness |
| OSM graph and GTFS | Prepare graph, attach stops, route to stop | `backend/tests/test_data_loader.py`, deployment preparation script | Existing; county path unverified | Acquire and measure real county graph |
| County boundary | Include Diridon, reject distant out-of-county point; filter stop feed | `backend/tests/test_county_coverage.py` | Added; not run | Validate OSM graph clipping and production bundle |
| City GIS | Query, cache, and attribute sidewalk data | `backend/tests/test_arcgis.py` | Existing; not run | Keep the known Diridon-only scope visible |
| GroundTruth | Compare nearby data, render priorities, show provenance | `backend/tests/test_groundtruth.py`, frontend E2E | Existing; not run | Verify no out-of-scope city comparison is implied |
| Community observations | Submit and list an unverified report | `backend/tests/test_observations.py`, frontend E2E | Existing; report-mode regression added; not run | Select durable storage before public release |
| REST API | Health, coverage, route, and evidence responses | `backend/tests/test_routing.py` | Existing; live API tests require prepared data | Execute full backend suite |
| MCP schemas and tools | Discover nine read-only tools; structured coverage result | `backend/tests/test_mcp.py` | Added; in-process only; not run | Exercise Streamable HTTP negotiation and real calls |
| MCP hosted endpoint | Connect external client to `/mcp` | `scripts/smoke_mcp.py` | Script added; not run | Deploy, then run against actual service URL |
| Accessibility | Keyboard and automated violation scan | Existing keyboard flows only | Not fully verified | Add axe run and manual keyboard/screen reader review |
| Mobile | Route selection and map sheet at narrow viewports | Existing Playwright configuration | Not run for Phase 5 changes | Run real mobile-sized browser journeys and inspect screenshots |
| Security | Input limits, host checks, and public reporting | Existing request validation plus MCP input bounds | Partial; not audited end to end | Review proxy trust, abuse limits, and storage controls |
| Production deployment | Refresh, assets, health, route, MCP, data storage | No deployment evidence gathered | Not verified | Deploy and inspect the stable host and assets |

## Commands for a fully configured checkout

These are documented execution targets, not claims that they passed here.

```sh
python -m pytest backend/tests -q
cd frontend && npm ci && npm run build
cd frontend && npx playwright install chromium && npm run test:e2e
TRANSITGAP_MCP_URL=https://<actual-host>/mcp python scripts/smoke_mcp.py
```
