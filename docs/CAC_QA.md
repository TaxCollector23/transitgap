# P0 QA log

Date: October 20, 2026. Local checkout only.

- Backend: **96 passed**, 121 Shapely deprecation warnings.
- Focused pilot/API/gap tests: **14 passed**, 20 warnings.
- ESLint: passed.
- Vite production build: passed; MapLibre JS chunk advisory at 1,086.49 kB.
- Real-data Playwright: initial full run **10 passed, 1 failed** because a map aria-label matched the VTA stop dropdown query. Selector was made exact; targeted gap scenario passed (**1 passed**) and the final full suite passed (**11 passed**).
- Reproduced pilot API response: stop `5459`, wheelchair, 10 min, n=150; 0 documented, 7 possible, 7 unknown-dependent sampled origins; 384 possible segments.
- Not run: live hosted smoke after a new deployment, field audit, rider study, CAC submission, or student algorithm contract (core not yet authored).

Failure screenshot/video/trace from the initial run are retained in `frontend/test-artifacts/test-results/`. No tests are represented as human validation.
