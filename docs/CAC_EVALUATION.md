# Evaluation plan and observed results

## Reproducible checks

- Backend unit/API suite: `cd backend && .venv/bin/python -m pytest -q` — 96 passed, 121 Shapely deprecation warnings.
- Frontend static checks: `cd frontend && npm run lint && npm run build` — passed. Build has a MapLibre chunk-size advisory.
- Local real-data browser suite: initial run 10 passed / 1 failed on an ambiguous test selector; after correction the targeted gap flow passed (1 passed) and the final full suite passed (11 passed).
- Documented/possible API smoke: stop 5459, wheelchair, 10 minutes, 150 sampled nodes returned 0 documented and 7 possible sampled origins; 7 origins depended on unknown conditions. The sample is not population weighted.

## Not evaluated / no evidence available

- No geospatial field truth set, route-ground-truth accuracy, consented rider sessions, or comparative user study.
- No claim that wheelchair routes are physically usable or that OSM unknown tags indicate real barriers.
- No deployment verification in this sprint and no CAC submission confirmation.

## Student-owned algorithm evaluation

The inspection-information-value implementation is intentionally pending student work. Contract cases are under `backend/student_work/`; the student should explicitly run `cd backend && .venv/bin/python -m pytest -q student_work/inspection_priority_contract.py` after implementation. Do not mark the algorithm gate passed until the student has implemented it, independently explained it, and the contract suite passes.
