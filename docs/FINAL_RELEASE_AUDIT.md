# Final engineering release audit

Date: October 20, 2026. Branch: `codex/mobility-refinement`; PR [#8](https://github.com/TaxCollector23/transitgap/pull/8), open. No merge authorized or performed.

## Baseline verified

The checkout was clean at `f47a452`. GitHub run `39508319249` had passing `checks`, failing `fixture-browser`, and intentionally skipped manual `real-data`. The failure was reproduced locally: the exact implicit-label locator could not select Observation, although health enabled reports and the select was present in the browser accessibility tree. The label wrapped the select/options. An explicit `htmlFor`/`id` association fixes the locator without weakening the test; the fixture now verifies health, HTTP 201, unverified review status, reload persistence, keyboard routing, and axe checks.

The inspection algorithm was a `NotImplementedError` stub; no separately authored patch was present. The current user brief authorizes AI-assisted implementation and integration. No student authorship is claimed.

## Implemented

- Directed time-bounded inspection sensitivity with unique origin/stop outcomes, stable IDs/ties, null unavailable records, duplicate physical-record handling, explicit distinct parallel alternatives, validated costs/budgets, and an independent exhaustive small-graph reference.
- Corrected the contract's incorrect score: both o1 and o2 reach s1 through u→s1, so blocking it changes two pairs. The independent reference uses exhaustive forward paths.
- Integrated bounded real OSM connection scoring into the existing reachability API and Access gaps view. Existing municipal proximity scores are labeled separately. No landing or map redesign.
- Corrected toward-stop partial-edge clipping and retained unknown-only portions when documented reach covers only part of the same edge.
- Added a named width-optional sensitivity policy, explicit missing-attribute counts, and dataset/build provenance. The default conservative policy remains unchanged.
- Added an A* lower-bound certification for compact snapshots; arbitrary nonmetric graphs use a zero heuristic. The reproduced 10-versus-2 cost error is covered by regression tests.
- Isolated fixture SQLite files per process; production reporting remains disabled without durable storage.

## Checks at this point

131 backend/contract tests pass (existing Shapely deprecation warnings remain). ESLint and production build pass; MapLibre retains its >500 kB bundle advisory. The expanded fixture suite passes 4 tests; the complete real-data local browser suite passes 11. GitHub run 39512410549 passes both required jobs. Final CI, live deployment, and measurements are recorded in RELEASE_ACCEPTANCE.md after completion.

## Boundaries

Scores are hypothetical reachability sensitivity on sampled graph journeys. They are not riders, physical accessibility verification, or official priorities. At most 12 candidates on deterministic shortest possible paths are evaluated; tied alternate paths may contain other useful inspection opportunities. OSM source snapshot date and human observations remain unknown. Durable production reporting, real screen-reader/voice-control validation, field studies, student contribution, video, deadline confirmation, and CAC submission are not fabricated or claimed complete.

## External browser recovery fixes

The first public deployment (`cfc74c6`) passed HTTP and MCP smoke but its full browser run had 8 passed / 3 failed. Two checks used a development-only MapLibre handle absent in production. The camera-stability test now pans with keyboard controls and checks the actual origin marker stays in place during stop search. The gap/mobile test uses visible canvas and internal content-width assertions.

The third failure revealed an application issue: `/accessibility/priorities?limit=80` returned in 109 ms, but a stalled `/data-sources` request held the entire evidence panel in loading because of `Promise.all`. Loads are now independent with bounded retry, separate candidate/report/availability states, and explicit optional-source failure/retry. Saving a report no longer waits for unrelated metadata. A fixture regression verifies that candidates and report controls remain usable when metadata requests fail. Local reruns: 4 fixture tests and all 11 real-data tests pass. Initial public failure traces are retained locally under `frontend/test-artifacts/production-before-fix/`.
