# Evaluation plan and observed results

## Reproducible checks

- Backend unit/API suite: `cd backend && .venv/bin/python -m pytest -q` — 96 passed, 121 Shapely deprecation warnings.
- Frontend static checks: `cd frontend && npm run lint && npm run build` — passed. Build has a MapLibre chunk-size advisory.
- Local real-data browser suite: initial run 10 passed / 1 failed on an ambiguous test selector; after correction the targeted gap flow passed (1 passed) and the final full suite passed (11 passed).
- Documented/possible API smoke: stop 5459, wheelchair, 10 minutes, 150 sampled nodes returned 0 documented and 7 possible sampled origins; 7 origins depended on unknown conditions. The sample is not population weighted.

## Not evaluated / no evidence available

- No geospatial field truth set, route-ground-truth accuracy, consented rider sessions, or comparative user study.
- Hosted Vercel `/`, `/app`, `/health`, pilot stop list and sample reachability all returned HTTP 200. Health reported a 34.76-second backend initialization and instance-local report storage with reports disabled.
- No claim that wheelchair routes are physically usable or that OSM unknown tags indicate real barriers.
- No CAC submission confirmation.

## Student-owned algorithm evaluation

The inspection-information-value implementation is intentionally pending student work. Contract cases are under `backend/student_work/`; the student should explicitly run `cd backend && .venv/bin/python -m pytest -q student_work/inspection_priority_contract.py` after implementation. Do not mark the algorithm gate passed until the student has implemented it, independently explained it, and the contract suite passes.

## Final engineering sprint update

The formerly pending algorithm is now AI-assisted code, integrated into the pilot response and UI. The contract's two-origin reference expectation was corrected to 2 and checked with independent exhaustive paths. The current complete backend/contract suite has 128 passing cases; 3 fixture and 11 local real-data browser tests pass. Final measured sensitivity and deployment evidence are in FINAL_RELEASE_AUDIT.md and RELEASE_ACCEPTANCE.md. Earlier measurements above are historical, not current release gates.
