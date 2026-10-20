# Final sprint QA

- Reproduced the exact CI Observation dropdown failure locally (one failed fixture journey). The form existed and reporting was enabled; explicit label association fixed the locator without relaxing assertions.
- Corrected the inspection contract's two-origin expected impact from 1 to 2; independent exhaustive forward-path enumeration agrees.
- Reproduced A* cost 10 vs optimal Dijkstra cost 2 with nonmetric stored lengths; certified lower-bound scaling / uncertified-graph zero heuristic corrects it.
- Final backend plus contract suite: 131 passed. Existing Shapely deprecations remain (warning count depends on prepared evidence-cache rebuild).
- CI-style non-integration suite is isolated from public data downloads; integration tests stay separately selectable.
- Fixture browser: 3 passed (save/reload persistence, disabled reporting, keyboard routes, speech controls, axe).
- Real-data local browser: 11 passed (five algorithms, profiles, desktop/mobile map, gaps, evidence, failure recovery, reload, automated accessibility).
- Lint/build pass. MapLibre retains its >500 kB advisory. Production npm audit reports zero vulnerabilities.
- Generated screenshots/traces are ignored by Git; failures remain available in GitHub Actions artifacts and history.

See RELEASE_ACCEPTANCE.md for final-head CI, deployment, and live browser checks. Real screen-reader/voice-control testing, field observations, independent student work and CAC submission are not claimed.
