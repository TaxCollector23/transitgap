# Final sprint QA

- Reproduced the exact CI Observation dropdown failure locally (one failed fixture journey). The form existed and reporting was enabled; explicit label association fixed the locator without relaxing assertions.
- Corrected the inspection contract's two-origin expected impact from 1 to 2; independent exhaustive forward-path enumeration agrees.
- Reproduced A* cost 10 vs optimal Dijkstra cost 2 with nonmetric stored lengths; certified lower-bound scaling / uncertified-graph zero heuristic corrects it.
- Final backend plus contract suite: 131 passed. Existing Shapely deprecations remain (warning count depends on prepared evidence-cache rebuild).
- CI-style non-integration suite is isolated from public data downloads; integration tests stay separately selectable.
- Fixture browser: 4 passed (save/reload persistence, disabled reporting, keyboard routes, speech controls, axe).
- Real-data local browser: 11 passed (five algorithms, profiles, desktop/mobile map, gaps, evidence, failure recovery, reload, automated accessibility).
- Lint/build pass. MapLibre retains its >500 kB advisory. Production npm audit reports zero vulnerabilities.
- Generated screenshots/traces are ignored by Git; failures remain available in GitHub Actions artifacts and history.

See RELEASE_ACCEPTANCE.md for final-head CI, deployment, and live browser checks. Real screen-reader/voice-control testing, field observations, independent student work and CAC submission are not claimed.

Mobile screenshot review caught clipped opaque candidate IDs in the new impact list. The display now uses readable OSM way numbers, with exact connection IDs retained in the API. The targeted pilot browser flow passes at both desktop and 390 px, including an internal result-region width assertion.

The first public browser run had 8 passed / 3 failed: two production-incompatible development-handle checks and one real all-or-nothing metadata loading defect. Tests now assert the actual visible camera behavior; the panel loads independent data streams and exposes source failures honestly. Local reruns after these corrections: 4 fixture / 11 real-data tests passed. Final public rerun follows deployment.

Final deployed code `ca3f34d`: public full browser suite **11 passed** after waiting for actual hero-image decoding. All original visual assertions remain. The first attempt on this deployment had **10 passed / 1 image-readiness failure**; an intermediate harness restart was interrupted and not counted as a pass. Final MCP protocol/tools/real route/gaps/invalid-input check passes. HTTP smoke passes every listed endpoint; cold health took 39.188 seconds. Full evidence and retained-artifact locations are in RELEASE_ACCEPTANCE.md.
