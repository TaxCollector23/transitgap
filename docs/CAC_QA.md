# P0 QA log

Date: October 20, 2026. Local checkout only.

- Backend: **96 passed**, 121 Shapely deprecation warnings.
- Student algorithm contract: 12 cases are specified, but the implementation is a deliberate `NotImplementedError` stub. During setup pytest initially auto-collected them and reported **12 failed / 96 passed**; the file was renamed outside default discovery. Those 12 failures are the pending student implementation gate, not regressions in the default suite.
- Focused pilot/API/gap tests: **14 passed**, 20 warnings.
- ESLint: passed.
- Vite production build: passed; MapLibre JS chunk advisory at 1,086.49 kB.
- Real-data Playwright: initial full run **10 passed, 1 failed** because a map aria-label matched the VTA stop dropdown query. Selector was made exact; targeted gap scenario passed (**1 passed**) and the final full suite passed (**11 passed**).
- Reproduced pilot API response: stop `5459`, wheelchair, 10 min, n=150; 0 documented, 7 possible, 7 unknown-dependent sampled origins; 384 possible segments.
- Hosted production smoke: `/` 200, `/app` 200, `/health` 200, pilot stop list 200 (99 stops), and stop reachability 200 with the same `5459` counts above. Health reported 34.76-second initialization; reports disabled because persistence is instance-local.
- Not run: field audit, rider study, CAC submission, or student algorithm contract (core not yet authored).

Failure screenshot/video/trace from the initial run are retained in `frontend/test-artifacts/test-results/`. No tests are represented as human validation.

## Final engineering sprint update

The algorithm stub is replaced by an explicitly AI-assisted implementation. The corrected contract and expanded independent tests are included in CI. Current local result: 128 backend/contract tests pass; 3 fixture browser tests pass; 11 real-data browser tests pass; lint/build pass. Earlier failures above are historical. Final CI and live-host results are recorded in RELEASE_ACCEPTANCE.md.
