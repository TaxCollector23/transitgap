# Release acceptance — October 20, 2026

**READY FOR ENGINEERING RELEASE.** CAC submission readiness remains awaiting human work.

Production code: `ca3f34d`, [TransitGap](https://transitgap.vercel.app), immutable deployment `transitgap-kox1idp4m-rangan-alt.vercel.app` (`dpl_H2nXQkWt3jxWuw1ZXQQZVU4JujY4`). `/health` confirms the code SHA. Subsequent changes in the report commit are tests/documentation only.

| Gate | Actual evidence | State / remaining action |
|---|---|---|
| A: Git / CI | PR #8 open and mergeable; code run [39514893673](https://github.com/TaxCollector23/transitgap/actions/runs/39514893673) has passing checks + fixture-browser | Pass; final report-head checks tracked on PR. No merge performed. |
| B: Backend | 131 local unit/integration/contract tests pass; CI 127 passed / 4 integration cases deselected | Pass; all 4 real-data cases were executed locally, not claimed as ordinary CI. |
| C: Routing | Five algorithms and profiles exercised; weighted cost/geometry/direction/profile tests; A* nonmetric counterexample fixed | Pass; BFS minimizes hops, not weighted distance. |
| D: Reachability | Actual 5459, 4514, 5460 pilot results plus named width sensitivity saved with graph hash | Pass; model/sample limitations retained. |
| E: Inspection metric | 29 initial contract/independent cases, real API adapter and browser output; top 5459 candidate changes 7 of 150 sample pairs | Pass; AI-assisted implementation, maximum 12 candidates, not an official priority. |
| F: Frontend | 11 local and final 11 public-site browser tests pass; metadata outage regression added | Pass. |
| G: Accessibility | Keyboard route entry, axe checks and synthetic local-speech controls pass | Pass automated; real screen-reader/voice-control sessions remain outstanding. |
| H: Mobile | 390×844 actual public route flow, mobile impact text-width assertion, landing at 5 widths; screenshots reviewed | Pass for tested flows; third-party map tiles remain a network dependency. |
| I: Data | Actual OSM/VTA, source links, explicit pilot boundary, graph SHA; source snapshot and observation dates stay unknown | Pass; no fabricated field evidence. |
| J: Reporting | Fixture saves unverified claim, verifies HTTP 201 and persistence after reload; production health reports reports_enabled=false / instance-local | Pass for honestly disabled production behavior; durable DB remains unprovisioned. |
| K: Deployment | Public HTTP smoke, final public Playwright 11/11, real MCP protocol/client calls all pass | Pass. |
| L: Submission | No genuine student contribution record, field/user sessions, video or CAC confirmation provided | Awaiting student; not an engineering-release claim of CAC submission. |

## External verification

`docs/benchmarks/production-smoke.json` records HTTP 200 for `/`, `/app`, hashed JS asset, `/health`, `/stops`, `/coverage`, pilot stops, pilot stop 5459 analysis, a real `/route` query, `/accessibility/priorities` and `/data-sources`. There are 3,348 county stops and 99 pilot stops. Production 5459 default result remains 0 documented / 7 possible / 150 sampled origins; 12 inspection candidates are evaluated. The new reachability metric and older route-proximity metric are separate.

The deployed MCP SDK client negotiated protocol `2026-07-28`, discovered 13 read-only tools, searched real Diridon stops, calculated a real route, retrieved gaps, and confirmed invalid input rejection. HTTP 200 alone was not used as MCP evidence.

## Actual failures and corrections

- Original GitHub/local fixture: one failed report journey. Implicit label text included select options; explicit label association fixes it.
- First public run: 8 passed / 3 failed. Two checks improperly depended on a development-only map handle; now they exercise observable camera/marker behavior. The third exposed candidates being hidden by one stalled source-metadata request; independent bounded/retryable loading fixes it.
- Next public run: 10 passed / 1 failed. Hero image readiness was evaluated before decoding; the test now awaits `HTMLImageElement.decode()` and keeps all visual assertions.
- An intermediate rerun was interrupted while correcting the image-readiness harness (2 passed, 1 failed, 1 interrupted, 7 not run). It is not counted as a passing suite.
- Final public rerun: **11 passed**. Fixture regression suite: **4 passed**. No test assertion was deleted to hide the original defect or the mathematically incorrect two-origin score.

Generated artifacts are ignored by Git under `frontend/test-artifacts/`; initial public failure traces remain in `production-before-fix/`, and final screenshots are in `screenshots/`. GitHub CI failures retain their own artifacts. No field visit or real assistive-technology session is inferred from these automated checks.

## Performance and practical limits

Local prepared-process initialization measured 11.575 s; a second in-process initialization using the graph cache measured 1.610 s. Graph/stop loading accounted for 9.888 s in the first pass. The benchmark harness peak was 1,519.62 MiB while reinitializing twice, not a measurement of production steady-state RSS.

Production reported 38.174 s initialization and the first health HTTP request took 39.188 s. The warm real wheelchair route took 0.194 s; pilot analysis took 1.874 s in this smoke. No startup-performance improvement is claimed. The map/planner use prepared CDN snapshots, but first dynamic queries can still wait for initialization. MapLibre's ~1.09 MB chunk and Shapely deprecation warnings remain P1/P2 work.

Production npm audit reports zero vulnerabilities; no environment secrets or generated test binaries are tracked. Moderation and unverified-report routing behavior have regression coverage. This is not a comprehensive Python dependency audit or a worst-case MCP payload-size benchmark; count/bbox/input bounds and read-only tool privileges were inspected.

## Human submission work

The inspection implementation and support are AI-assisted. Independently authored student code/analysis, personal experiences, actual field observations, consented user studies, a real 1–3 minute video, deadline/eligibility confirmation and a submission receipt must be provided by the student. No prediction of competition outcome is made. See AI_ASSISTANCE.md, STUDENT_CONTRIBUTIONS.md, field protocol, and final video/shot-list docs.
