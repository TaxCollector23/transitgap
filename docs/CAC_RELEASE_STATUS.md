# CAC P0 release status

**P0 RELEASE STATUS: NOT READY**

| Gate | State | Evidence / blocker |
|---|---|---|
| Existing landing and planner | Pass locally | Desktop/mobile Playwright flows; source UI preserved |
| Real county route and algorithms | Pass locally | Playwright selects a real Diridon journey; all five algorithms and five profiles return routes |
| Documented/possible pilot | Pass locally | Real VTA/OSM API and browser flow; details below |
| API and frontend checks | Pass locally | 96 backend tests; lint/build pass |
| Browser checks | Pass locally | First full run 10 passed / 1 failed due ambiguous test selector; corrected targeted flow 1 passed; final full suite **11 passed**. |
| Student-owned significant algorithm | **Awaiting student** | Contract/spec and test cases prepared; core intentionally unimplemented |
| Field observations / rider sessions | **Awaiting human work** | None recorded |
| Hosted release | **Not verified this sprint** | No fresh deployment or hosted smoke check performed |
| Durable report persistence | Blocked by provider setup | No configured database; public reports remain paused |
| CAC entry / receipt | **Awaiting user** | No submission proof available |
| Demo video | **Awaiting student** | No public video recorded |

## Reproduced pilot response

API request: `GET /accessibility/reachability/5459?profile=wheelchair&minutes=10&sample_size=150`.

- Actual GTFS stop `5459`, “1st & Paseo de San Antonio”; nearest graph node 24.3 m away (within the explicit 35 m study threshold).
- Pilot selection: 99 actual VTA stops within 1,500 m of Diridon; 97 nearest-node distances are within 35 m.
- Deterministic sample: 150 OSM graph nodes, not people or population.
- Result: `INSUFFICIENT_DOCUMENTED_DATA`; 0/150 origins reached in the documented scenario, 7/150 in the possible scenario, 384 possible edge segments, and 7 sampled origins whose possible reach depends on unknown conditions.
- Examples include OSM ways [25902649](https://www.openstreetmap.org/way/25902649) (crossing kerb unknown) and [25902647](https://www.openstreetmap.org/way/25902647) (surface and width unknown). These are source records, not verified physical barriers.
- VTA feed version `2026-10-09_14:57`. OSM cache modified and manifest generated October 20, 2026; source snapshot date and field observation date are unrecorded.

This negative/limited result is retained as evidence. It is not converted into a claim of inaccessibility.

## Exact checks

- `backend/.venv/bin/python -m pytest -q`: **96 passed, 121 Shapely deprecation warnings**.
- Focused documented reachability / API / gap suite: **14 passed, 20 warnings**.
- `frontend/npm run lint`: passed.
- `frontend/npm run build`: passed; Vite reports the MapLibre chunk at 1,086.49 kB (>500 kB advisory).
- `frontend/npm run test:e2e -- --reporter=line`: initial run **10 passed, 1 failed** (ambiguous `getByLabel("VTA stop")`, because the map name also matched); final run after the exact selector fix: **11 passed**.
- `frontend/npm run test:e2e -- --grep 'network gaps render' --reporter=line`: **1 passed** after the selector fix.

## Hosting and submission

Local checks do not prove hosted behavior. No new production deployment was made. Existing report persistence limitation is unchanged. Do not submit until the student completes and understands their algorithm component, the outstanding browser run and critical gates are reviewed, and the CAC portal confirms the applicable deadline.
