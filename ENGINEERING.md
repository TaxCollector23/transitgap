# TransitGap engineering notes

TransitGap routes over a locally cached OpenStreetMap pedestrian network to official VTA GTFS stops near San José Diridon Station. This document describes the implementation, its evidence limits, and practical ways to extend it.

## Graph construction and cache

`backend/app/data_loader.py` asks OSMnx for a directed `MultiDiGraph` using `network_type="walk"`, `retain_all=True`, and simplified paths. OSMnx retains intermediate way geometry on simplified edges. The graph remains directed: a path from A to B is not assumed to imply a path from B to A. Parallel OSM edges retain their edge keys and independent tags.

The downloader configures OSMnx to retain these way and node attributes when present: `highway`, `footway`, `sidewalk`, `crossing`, `kerb`, `surface`, `smoothness`, `incline`, `wheelchair`, `tactile_paving`, `barrier`, `width`, `access`, `foot`, and `indoor` (where applicable to ways). Missing values are not filled in. The adjacent `.metadata.json` records the graph radius, OSMnx version, graph file stat, configured tag allow-lists, and counts of tags actually stored. For an older cache, absence from the GraphML may mean a tag was not retained when that cache was created; the metadata calls out this uncertainty.

The GTFS archive is cached from VTA's official feed, and the filtered stop list is cached against both feed and graph file stats. Normal routing reads the in-memory graph and makes no external data requests. To intentionally refresh the local dataset before packaging it, run `TRANSITGAP_REFRESH_DATA=true python scripts/prepare_deployment_data.py` from the repository root. The variable is a one-run command setting; do not configure it as a persistent runtime variable. A successful graph refresh atomically replaces the old file and writes a new manifest.

The origin is snapped to its geodesically nearest graph node using a cached unit-sphere KD-tree (SciPy, provided by OSMnx); a geodesic scan is used if SciPy is unavailable. Origins over 120 m from the graph are rejected. Stops farther than 150 m from the graph are omitted from the selected region. Disconnected components remain in the graph: if the nearest origin node cannot reach a stop in the directed network, the API returns an unavailable route rather than snapping to a different component.

The `walk` network is an OSM pedestrian graph. It is **not** a verified sidewalk inventory. A mapped road/path does not prove a sidewalk exists, and mapped data may be stale or incomplete. OSM tags are not independent field measurements.

## Algorithms and costs

The application calls NetworkX's standard implementations of Dijkstra, bidirectional Dijkstra, and A*. These are three distinct algorithms over the same directed graph and profile-specific edge-weight callback. NetworkX returns a node sequence; for each adjacent pair, TransitGap selects the minimum eligible parallel arc using the same cost and stable insertion-order tie rule, then uses that arc's actual key, attributes, length, and geometry. Edge direction is preserved.

Let `d(e)` be the nonnegative OSM edge length in meters:

- `standard`: `cost(e) = d(e)`.
- `avoid_mapped_stairs`: explicitly mapped `highway=steps`, `footway=steps`, or `indoor=steps` edges are hidden; other eligible edges cost `d(e)`.
- `prefer_documented_paths`: `cost(e) = d(e) * (1 + sum(w(a) for each applicable missing attribute a))`.

The preference profile currently considers missing `surface`, `smoothness`, `incline`, `wheelchair`, and `width` tags on route edges, plus `sidewalk` on common drivable road classes, and `crossing`, `kerb`, and `tactile_paving` at mapped crossings. Default weights are in `backend/app/accessibility.py`; each can be overridden using a `TRANSITGAP_UNCERTAINTY_PENALTY_<ATTRIBUTE>` environment variable. Every weight must be finite and nonnegative. These are configurable algorithm preferences, not physical accessibility measurements or safety guarantees. More documentation does not imply greater accessibility.

A* uses great-circle distance between graph nodes in meters. Since every edge cost is at least its physical length, straight-line distance remains an admissible lower bound, including for the documentation preference profile. The physical route distance is the sum of selected OSM edge lengths plus origin/stop connector distances. `optimization_cost_m` is reported separately and is not labeled as travel distance. Estimated time divides physical distance by the stated 1.2 m/s assumption.

## Accessibility observations

`backend/app/accessibility.py` handles shared tag interpretation. The route response keeps observed OSM tags and missing applicable tags separate. It reports surface-tagged and untagged distance with a distance denominator; applicable crossing observations with known or missing kerb information and a crossing denominator; mapped stairs; tagged barriers; explicit pedestrian access tags; and segment-level applicable tag observations. Fields that do not apply are omitted from that segment's denominator. A blank tag is unknown, never a value of zero or an automatic barrier.

The route's profile and algorithm are returned with physical distance, weighted optimization cost, and computation time. `POST /route/compare` runs shortest, mapped-stair-avoiding, and documentation-preference objectives over the same graph, and gives each objective either its own route or an explicit unavailable result. It never substitutes a different profile's path.

## Source and code ownership

- NetworkX supplies the shortest-path algorithm implementations; OSMnx supplies the OSM download, pedestrian graph, and GraphML serialization; Shapely supplies geometry parsing/GeoJSON mapping; FastAPI and Pydantic supply HTTP and request validation.
- Project-specific code includes geodesic snapping and cache handling, profile weights and access filtering, parallel-edge selection, edge-geometry orientation/continuity, accessibility observations, route comparison, API integration, and tests.
- AI tools helped generate and revise implementation code and tests. Do not present generated code as independently student-written. The project author should review, explain, and modify the submitted code in accordance with contest and school rules.

## Tests and benchmark

Unit tests use small synthetic directed multigraphs for algorithm parity, one-way links, components, parallel edge keys, curved geometry, access restrictions, invalid weights, tag uncertainty, crossings, and node tags. Integration tests read the real cached OSM graph and VTA feed and exercise the API and all three algorithms and profiles. Browser tests run the real Vite app in Chromium against the local FastAPI backend. Synthetic fixtures test isolated logic; only the integration and browser flows claim to use the local production datasets.

```bash
cd backend
python -m pytest -q
python -m uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm run build
npm run test:e2e
```

```bash
cd backend
python benchmarks/benchmark_routing.py --pairs 30 --repeats 5 --seed 7331
```

The benchmark chooses ordered pairs from real GTFS stops snapped to graph nodes using a fixed seed, uses the standard distance objective, and times the routing call separately from route serialization. It writes every successful and failed repeat to `backend/benchmarks/results.csv`; `summary.md` reports median and nearest-rank p95 over all attempts and cost agreement for pairs where all three algorithms succeeded in every repeat. It does not discard no-path failures or claim a universal speed ranking. Results must be generated by running the script on the target cache and machine; no results should be hand-entered.

## Student-owned extension ideas

1. Independently implement Dijkstra or A* on a tiny directed graph and compare its path cost against NetworkX.
2. Add a synthetic parallel-edge case of your own and explain how edge keys keep geometry aligned with the selected cost.
3. Choose and justify the missing-tag weights using a written study plan, then report how routes change without describing them as accessibility guarantees.
4. Survey mapped crossings on the ground, record source and date, and compare observations with OSM without silently rewriting OSM data.
5. Repeat the benchmark on several graph sizes and machines before making a performance claim.

## GroundTruth source comparison

`backend/app/data_sources/arcgis.py` reads City service metadata, fetches object IDs in a bounded WGS84 envelope, requests small GeoJSON batches and caches original IDs, attributes and retrieval metadata. The deployment data preparation step packages the local radius snapshot when available. Runtime startup reads that snapshot without making a municipal network request. `backend/app/groundtruth.py` repairs invalid polygon geometries when possible, clips them to the study circle, projects City and explicit OSM pedestrian-path geometries to EPSG:26910, and uses Shapely's STRtree for local candidates. A 5 m match and 14 m review band mean spatial proximity only; opposite-side ambiguity and intersection topology remain sources of false matches.

Inspection candidates carry source provenance and known/unknown attribute summaries. The fixed-seed route sample ranks candidates by normalized sampled route impact, distinct VTA stops, missing information and source conflict. Its score is a review aid, not traffic demand, ridership or an official priority. `GET /data-sources`, `/accessibility/gaps`, `/accessibility/priorities`, and `/accessibility/municipal-sidewalks` expose these results. Route responses include nearby municipal polygon context with an explicit proximity caveat.

Community reports are text and coordinates stored through a parameterized SQLite layer. New reports begin `COMMUNITY_REPORTED` and `UNREVIEWED`, are not route constraints, and are rate-limited in-process. Local SQLite is filesystem-persistent. Vercel's default `/tmp` path is instance-local; use a configured durable database mount before treating hosted reports as persistent.
