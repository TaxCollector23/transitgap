# Performance and production reporting release audit

Measured October 20, 2026, on the existing county data. See the raw JSON in
`docs/benchmarks/performance-before.json`, `performance-after.json`,
`performance-reachability.json`, `graph-equivalence.json`, and
`region-experiment.json`. Fresh process means a new Python interpreter, not a
flushed filesystem cache. The Mac and Vercel measurements must not be conflated.

## Local measured results

| Measurement | Before | After |
|---|---:|---:|
| Fresh initialization, excluding imports | 12.186 s | 8.972 s |
| Graph load | 10.455 s | 6.745 s |
| Repeated full initialization in the same process | 1.628 s | 1.966 s |
| Steady RSS after benchmark | 1325.30 MiB | 1320.28 MiB |
| Peak RSS | 1546.23 MiB | 1539.17 MiB |
| Planner JavaScript (uncompressed) | 1,134.62 KB | 47.52 KB |

The final saved local run improved initialization about 26% and graph loading
about 35%. Earlier after-runs ranged from 6.78 to 8.97 seconds as other local
workloads varied; this is not a controlled confidence interval. Memory is
essentially unchanged. Repeated full reinitialization regressed slightly and is
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
sheet, keyboard alternatives and Read Aloud remain. Typography and the pixel-art
landing page are preserved. No new cosmetic feature was added.

The basic location → destination → default walking → route flow has four pointer
actions when counting input focus, both before and after. Selecting another
profile adds one action. This is a scripted interaction count, not evidence of
unassisted human task success. Automated tests do not establish human usability.

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
that case. It is rerun separately after disabling unnecessary video capture.

## Release status

Local engineering gates above pass. Deployment-specific initialization, real
public route timing, reporting readiness, after screenshots and MCP results are
recorded separately after deployment in the production performance artifact.
Do not infer a new public cold-start number from the local benchmark.

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
