# Testing and verification

## Local commands

```sh
python -m pytest backend/tests
cd frontend && npm ci && npm run build
cd frontend && npx playwright test
```

Run the FastAPI backend and Vite frontend using the commands in `README.md` before the browser suite. Playwright exercises the real local API; the integration flow should not mock route or GroundTruth endpoints.

## Phase 4 coverage

The Phase 4 suite should cover ArcGIS metadata, bounded ID batching, cache fallback, geometry conversion, correspondence thresholds, source availability, deterministic route impact, report validation and persistence, and the existing route algorithms. Desktop and mobile browser flows should cover route calculation, overlay toggles, candidate provenance, report placement/submission, and reload persistence.

No Phase 4 test or production build result is claimed in this document until commands have run in an environment that can execute the project toolchain. SQLite reports on Vercel are instance-local unless a durable storage path is configured; local SQLite restart persistence does not prove hosted durability.
