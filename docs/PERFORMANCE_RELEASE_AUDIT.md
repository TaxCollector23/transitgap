# Performance and production reporting release audit

Measured October 20, 2026, on the existing county data. See the raw JSON in
`docs/benchmarks/performance-before.json`, `performance-after.json`,
`performance-reachability.json`, `graph-equivalence.json`, and
`region-experiment.json`. Fresh process means a new Python interpreter, not a
flushed filesystem cache. The Mac and Vercel measurements must not be conflated.

## Local measured results

| Measurement | Before | After |
|---|---:|---:|
| Fresh initialization, excluding imports | 12.186 s | 6.759 s |
| Graph load | 10.455 s | 5.028 s |
| Repeated full initialization in the same process | 1.628 s | 1.663 s |
| Steady RSS after benchmark | 1325.30 MiB | 1375.47 MiB |
| Peak RSS | 1546.23 MiB | 1595.47 MiB |
| Planner JavaScript (uncompressed) | 1,134.62 KB | 47.66 KB |

The final saved local run (after the deployment cache fix) improved initialization about 45% and graph loading
about 52%. Earlier after-runs ranged from 6.76 to 8.97 seconds as other local
workloads varied; this is not a controlled confidence interval. Memory is
slightly higher (about 50 MiB); no RAM reduction is claimed. Repeated full reinitialization is essentially unchanged and is
not a warm route request: the real application initializes once per worker.
MapLibre's roughly 1.09 MB chunk still downloads; code splitting lets the planner
and destination search become usable without waiting for map JavaScript.
No reduction of total map-library code is claimed.

The baseline profiler attributed 12.43 cumulative profiled seconds to 1.1 million
JSON decodes, including 5.07 seconds in object hooks, and 1.96 seconds to 811,314
scalar geographic checks. Profiling overhead makes those different from the
unprofiled wall clock. The replacement uses bounded 4,096-record plain JSON
blocks, orjson decoding, shared immutable strings, and a tested NetworkX 3.x
storage adapter. Vectorized edge checks recalculate the conservative A* bound
from actual lengths and endpoints; an invalid bound falls back to zero. No
pickle, executable graph cache or unverified stored heuristic certificate is used.

The full semantic fingerprint is identical across all 291,569 nodes, all 811,314
directed keyed edges and their attributes/geometry. Only the recalculated numeric
A* certificate is excluded from that fingerprint and independently tested.
Twelve agency/profile outputs have identical geometry, edge selection, arrival,
distance, cost, directions and accessibility-summary hashes. Rail and GTFS caches
remain available; their measured baseline loading costs were about 0.20 s and
0.16 s, so replacing the working parser was not justified. The existing spherical
nearest-node index is reused per graph. Its build can occur inside rail loading,
so a separately timed subsequent index lookup is not its construction cost.

Station entrance attempts now share one current reviewed-effects database read.
No routing-effect cache can hide a moderation revocation. Stops/studies continue
to come from prepared CDN data; lightweight bounded warmup avoids repeatedly
serializing full health/data-source responses during startup.

Network-reachability analyses of three real Diridon stops and two documentation
policies took 0.70–1.11 seconds each in the saved experiment. The required policy
found zero documented sampled origins in those samples; the possible scenario
found 7, 0 and 9 respectively. Making width optional changed stop 5459's documented
count from 0 to 1, and did not change the other two. These are honest outcomes of
explicit conservative predicates, not proof that a whole area is inaccessible.
Missing unrelated tags do not exclude an edge; required fields depend on profile,
pedestrian-way/crossing relevance, and stated policy. The live route planner can
still use uncertain edges with visible uncertainty. Inspection counts are
independent tested hypothetical sampled pairs, not traffic, people or safety.

## Alternatives investigated

The existing cached Diridon-only graph loaded with imports/stops in 1.243 s at
202.30 MiB peak, but contains only 5,809 nodes, 15,770 edges and 94 VTA stops.
That smaller region does not satisfy county coverage. It was measured, not
deployed. Partitioning would need boundary-spanning routes and entrance/index
correctness before adoption. An always-running county worker could avoid graph
reconstruction between requests, but this sprint did not provision paid hosting
or prove any provider guarantees permanent free uptime at the measured RAM.
Vercel remains serverless, and cold instances still perform real work. No switch
of routing engine, language or routing database was made.

## Browser behavior and usability

Before captures and frontend resource measurements are in `docs/validation` and
`frontend/test-artifacts/performance`. The initial production attempt could not
activate Find route after readiness retries expired. Find route now accepts a
valid trip while the engine warms, announces preparation, waits at most 45 seconds
for readiness, and offers retry without losing the trip. Route requests have a
25-second timeout; address search and report submission have 15-second timeouts.
Backend liveness responds during initialization. A separate POST `/routing/initialize` holds an active invocation for up to 18 seconds, awaiting the shielded loader future so serverless compute can continue after brief liveness responses. Startup failure
does not hide the map or unified destination search.

The optional agency filter moved behind a disclosure. The search still covers
all agencies by default and results name their agency/station. Rail platforms are
grouped. Directions, profile recalculation, marker hiding, A/B markers, mobile
sheet, keyboard alternatives and Read Aloud remain. The font family, colors and pixel-art landing page are preserved; essential helper/source text is at least 14 px. The municipal source wording now correctly describes sidewalk records rather than implying a curb-ramp inventory. No new cosmetic feature was added.

The baseline planned location → destination → default walking → route flow could not complete because Find route stayed disabled in the observed attempt. The current public app completed that trip with four actual clicks at each of the four viewport sizes, counting input focus. Location permission was pregranted in the fixture; a first-time permission prompt and scrolling are not included. Selecting another profile adds one action. These scripted results are not evidence of unassisted human task success. Automated tests do not establish human usability.

## Validation and failures

- Python unit/integration/routing/profile, PostgreSQL and existing inspection
  contract suite: 164 passed. Three PostgreSQL cases use an isolated test database
  and per-test schemas. Routing algorithms and profiles run on independent small
  graphs and real county journeys. Expired/future feeds withhold departure times.
- Frontend lint, TypeScript and production build: passed. MapLibre still produces
  a large-chunk advisory, now isolated from the planner.
- Production-build Playwright: 28 passed, including VTA/Caltrain/BART at 390x844,
  768x1024, 1440x900 and 1920x1080, all four mobility profiles, keyboard planning,
  route failure/retry, mobile map selection, speech controls and axe checks.
- Fixture Playwright: 4 passed against local SQLite, then 4 passed against the
  isolated PostgreSQL test database, covering report save and mobile controls.
- Built startup tests: 5 passed, including map interaction at all four sizes with
  routing stalled and actionable/retryable trips after cold-start failure.
- First browser matrix had 27 passes and one navigation loss in the Vite development
  server. Tests now run the production build through a local API proxy; all 28
  pass. One new tablet startup test originally clicked outside its fixture's
  coverage; the app correctly rejected it. A valid in-coverage point passes.
- The independent student reference contract: 4 FAILED with NotImplementedError.
  This is an explicit student task outside default CI discovery, not a completed
  implementation or a passing release gate. The existing production inspection
  contract passes. AI attribution remains explicit.

The source-linked eight-location field shortlist leaves observation/date/agreement
fields blank. No participants, testimonials, visits, agency approvals, safe-route
certifications or student authorship were invented. Real assistive-technology
testing was not performed; axe, semantic keyboard tests and mocked speech controls
do not replace VoiceOver/NVDA or user sessions.

## Durable reporting

The existing adapter was extended and migrated, not replaced. PostgreSQL is in
an existing Neon Free project, using a separate database and ordinary runtime role.
No paid subscription was created. Database-backed limits are atomic across
instances, inserts are idempotent, public reports begin unverified, and moderation
history is retained. The runtime cannot create schemas or delete review history.
Only authenticated, supported, edge-linked, unexpired reviews affect routes.
Unverified potholes do not block paths. See REPORTING_OPERATIONS.md for credentials,
migrations, privacy, reviewer tools, retention and provider limits.

## Deployment failure caught and corrected

The first new production deployment (`5689153`, dpl_HrKUFqJnMGYvTWCg5FT2CpCyYT1o)
returned liveness but remained in walking_network after 100 seconds of polling.
The first route probe returned 503 in 0.119 seconds. The complete failed probe
is retained in production-async-failure.json. This demonstrated that a background
thread with short requests was not sufficient on Vercel. The prior working
release was restored. A bounded, awaited initialization endpoint now keeps the
invocation active without blocking other asynchronous requests, and preserves
its future across request timeouts. Two new backend tests cover concurrent
liveness and non-cancelling timeouts; all five built startup tests pass. Public
verification of the corrected candidate follows before promotion. PostgreSQL
effects are also always queried when configured, even if startup marked the store
unavailable; outages cannot silently discard reviewed barriers.

The held-warmup candidate reached readiness and returned a real wheelchair route,
but reported 71.081 seconds of initialization wall time, so it was not promoted.
Its health response is retained in production-warmup-before-cache-fix.json.
Inspection then found prepared GTFS/stop cache identities based on nanosecond
file mtimes and runtime manifest generation after timestamp mismatches. Cache
identities now use content hashes, and immutable Vercel runtime never regenerates
build manifests. Tests change only timestamps and reject accidental reparsing.
Production health now exposes per-phase wall/CPU timings, GTFS cache hits and
process RSS so deployed results can be interpreted rather than guessed.

A repeat 28-case browser run had 27 passes and an ENOSPC failure while closing
and writing artifacts for the algorithm case; there was no assertion failure in
that case. It passed on a separate targeted rerun after disabling unnecessary video capture (1 passed). The subsequent final backend suite has 164 passes, including deployment timestamp/cache and warmup tests.

## Release status

The verified production candidate is `a5d8185`, deployment
`dpl_BRDqWJcFKEYWifS5G1bbzWbU78KY`, promoted to https://transitgap.vercel.app/ .
All 24 public route requests passed (three agencies × four profiles × two repeats).
They ranged from 0.147 to 1.604 seconds, median 0.353 seconds in this sample.
The observed readiness request took 0.444 seconds after candidate validation;
this is a warm observation, not a forced cold start. The first protected candidate
warmup request took 1.831 seconds including CLI overhead and also was not a
controlled cold sample.

Public health reports all GTFS caches hit and approximately 1,246 MiB resident /
1,249 MiB peak RAM for that worker. It reports 17.626 seconds CPU but 192.172 seconds
initialization wall time: 174.539 seconds were in report-store initialization,
with only 0.148 CPU seconds there. A separate worker reported 18.813 CPU seconds /
48.245 wall seconds, including a 30.847-second evidence phase with only 1.609 CPU
seconds. These wall/CPU gaps demonstrate why a suspended serverless worker's
lifetime timer is not a user navigation-latency measurement. Provider suspension,
prewarming, I/O waits and worker placement are not controlled. No guaranteed
production cold latency or universal speedup from those incomparable wall timers
is claimed. A completely cold worker still needs substantial active graph work;
Vercel remains an explicit limitation. Metadata generation is now build-only and GTFS/stop caches survive packaging timestamp changes, so the verified worker hits all three schedule caches. Bounded held warmup avoids relying on an
unattended background thread alone.

One production validation harness attempt failed on nullable station_name before the agency route loop; the harness now falls back to stop_name and all 24 checks pass. The protected unpromoted URL required Vercel-authenticated CLI checks; this was deployment protection, not an application test failure.

The exact phase timings, cache hits, RSS, first request, all route timings and
source SHA are in `production-performance.json` and `production-candidate.json`.
Public reporting is enabled on PostgreSQL. Anonymous moderation returns 403;
authenticated review queue returns 200 (empty at verification). No synthetic
production observation was inserted. Actual report save/reload/review/revocation
was verified on the isolated PostgreSQL database. MCP protocol 2026-07-28 passed
13-tool discovery, coverage, stop search, real wheelchair route segments, gap
retrieval and invalid-argument handling.

Public browser checks captured all four required viewports with the map ready,
performed real four-click walking trips at all four sizes, and confirmed no route failure. After
measurements/screenshots are in `browser-after.json` and `docs/validation`.
Observed planner readiness was 0.819–1.690 seconds and map readiness 1.493–2.509
seconds on this machine/network sample. These are observations, not device-wide
latency guarantees. The baseline planned four-action flow failed at readiness, while all four current viewport trips completed with four clicks. The previous observed startup failure is explicitly retained in the before artifact.

The legacy-format control for all six real network analyses is in
`performance-reachability-before.json`. It took 0.498–0.578 seconds per study on
that run; the after run took 0.698–1.114 seconds. Analysis code was not optimized,
and timing varied with local load. Documented/possible counts and full inspection
candidate results are exactly equal. No reachability-analysis speedup is claimed.

PR #9 remains a duplicate source PR to the older mobility branch; its implementation
was integrated through reviewed PR #10 and release PR #8. It was not merged again.
The current sprint uses PR #11. Local resource pressure caused one failed legacy
control attempt without an artifact; the later isolated run completed. The Mac
had roughly 1.3 GiB disk free during the ENOSPC episode; unrelated files were not
deleted. The final release gates are passing code/fixture CI plus the actual local
and public checks above. Engineering readiness is conditional on the documented
serverless latency, source-data and provider limits; it is not safety certification.

CAC submission is **not complete**. The independent student implementation, human
field checks, genuine usability/screen-reader sessions, video, eligibility/portal
answers and actual submission receipt require the student. Official deadline
sources conflict; see CAC_2026_SUBMISSION.md and verify the portal. Engineering
release validation does not establish contest eligibility or completion.

## Reproduce

1. Install dependencies, run `python scripts/prepare_deployment_data.py`.
2. Run `python scripts/benchmark_startup.py --output report.json` in a fresh process.
3. Run `python scripts/verify_snapshot_equivalence.py OLD NEW --output equivalence.json`.
4. Run `python scripts/evaluate_pilot.py --output pilot.json` and
   `python scripts/generate_field_shortlist.py`.
5. Set the isolated test DATABASE URL as documented and run pytest with the
   existing inspection contract; run frontend lint/build, all three Playwright
   configs, and `BENCHMARK_LABEL=after node benchmark-browser.mjs` for public checks.

Final safety review: pytest and the fixture server now discard inherited production database credentials. All 164 backend tests and four PostgreSQL browser checks passed with a deliberately invalid inherited production DATABASE_URL and a separate explicit test database. GitHub code/fixture checks pass; its manually dispatched real-data job is skipped, with real-data integration/browser work executed locally as documented.

A final PostgreSQL regression test reproduced a reviewed-effect mismatch when JSON edge references contained spaces/numeric IDs. The API now stores canonical string triples and effect loading normalizes legacy rows, preserving review history. The full backend suite returned 164 passes after the fix; malformed object references are rejected rather than treated as triples. Final landing lint/type/build and two five-viewport/keyboard landing tests passed after the provenance/readability correction.

The final station-entrance regression brings the complete backend suite to **165 passed, 124 warnings (10.95 s)**, including isolated PostgreSQL and the existing inspection-priority contract. Wheelchair/stroller trips now reject a station whose recorded entrances are all explicitly inaccessible instead of falling back to its platform. Graph node zero remains a valid entrance. This does not certify unrecorded station access.

## Final production follow-up, October 21

PR #11 merged as `5e7640a`; Vercel deployment `dpl_BzBc3a8EWawhaKhJfnUJd12dijaS`
is Ready and assigned to the public domain. CLI polling timed out, but inspect
confirmed deployment success. Public health verified that exact build SHA.

The final live checks did **not** pass cleanly. The first attempt needed 55.0 s
to observe readiness after two 25 s network timeouts; that worker reported
20.43 s initialization. The first real route succeeded in 0.214 s, followed by
ten successful matrix requests before another request timed out. At four browser
sizes the map loaded in 1.5–2.1 s; the first 390 px trip timed out, while the
other three completed with four clicks. A second run observed readiness after
36.5 s, then timed out; its browser run timed out waiting for planner data.
These failures are preserved in `production-final-first-attempt.json`,
`production-final-second-attempt.json`, `browser-final-first-attempt.json` and
`browser-final-second-attempt.txt`. The prior 24-route and four-viewport successful
run remains valid evidence for that earlier run, not a guarantee of current
reliability. The final MCP check passed all 13 tools and a real wheelchair route.

The scheduled monitor also failed because it checked readiness once without
holding initialization active. It now POSTs the warmup endpoint with a 90 s
overall budget, bounded request timeouts, explicit failure handling and four
unit tests. Its direct production check passed after two probes. The full backend
suite now has **169 passes, 124 warnings (10.90 s)**. This monitor is a readiness
check, not a route test or an uptime guarantee.

**Release assessment:** code/fixture CI and local regression gates pass, but
the production cold-start/reliability acceptance gate remains unmet. The map and
search can load independently, with bounded retry and actionable failure; a
consistently seamless first production route is not established. An always-running
county worker needs sufficient measured RAM and hosting that guarantees uptime;
no paid resource was provisioned. CAC submission is still incomplete for the
human tasks above.
