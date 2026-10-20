# Release status: October 20, 2026

## Verified work

| Capability | Implementation and evidence |
| --- | --- |
| County routing | Real Santa Clara County graph and 3,348 connected VTA stops; county polygon validation. |
| Spatial performance | Cached spherical KD-tree. A synthetic 5,000-node route passes a two-second request budget. No per-request largest-component scan. |
| Mobility profiles | Standard, wheelchair, stroller, low vision and documented-path preference. Legacy stair-avoidance alias retained. |
| Segment evidence | Mapped, unknown and concern segments, explicit reasons, dashed unknown lines and attribute coverage. No fabricated field verification. |
| Mobility detour | Standard and profile routes overlaid with actual distance/time differences and explicit speed assumptions. |
| Access-gap study | 32 sampled stops precomputed. Reverse-network reach, partial edges, reciprocal-edge deduplication and display polygons. Ranking scope is labelled. |
| Stop service | Streamed GTFS joins, service calendars, exceptions, overnight times, boarding status and scheduled departures. |
| Directions | Derived from actual selected edge geometries, names and bearings, with segment caveats. |
| Address search | Explicit Nominatim proxy, geographic bounds, identifying User-Agent, in-process rate limit and bounded memory cache. No autocomplete. |
| Civic letter | Actual selected stop and model results, editable text and download. Never automatically sent. |
| Landing page | Scrolling restored on desktop and mobile. Actual network preview and measured sample results. Decorative logos, eyebrows and beneath-card captions removed. |
| Planner UI | Route, Access gaps and Evidence views. Advanced algorithm drawer. Miles, loader and separate origin/destination/report interactions. |
| Planner performance | Route features memoized; typing no longer refits the map. Municipal evidence loads only when opened. MapLibre now downloads separately from the 28.31 KB planner chunk. |
| Prepared data | The production build exports actual stop data, sample networks and letter drafts. A browser regression blocks every live data endpoint and still opens the planner, study and editable letter. No offline route calculation is claimed. |
| Sharing | Explicit origin/stop/profile journey links; no automatic home-location storage. |
| MCP | Existing public server committed and pushed in `a479865`; 13 read-only tools verified on the public server. Official-client HTTP, in-memory and stdio paths exercised. |
| Browser verification | Nine passing Playwright checks, including automated WCAG A/AA checks on landing, planner and gap views. Automated checks are not a full accessibility certification. |
| Backend verification | 66 passing pytest tests, including the final evidence snapshot roundtrip and source invalidation check. |
| Production build | Passes after MapLibre splitting. Remaining large chunk is the lazy map renderer. |

## Open work and limits

- The runtime release is validated through the stable public hostname after deployment. The public website, five algorithms, mobility comparison, stop service, address search and 13-tool MCP were exercised successfully.
- The county engine took 33.718 seconds to initialize in the recorded production cold start (10.492 seconds locally). Prepared stop data, sampled studies and letter drafts are exported for CDN delivery so those views can work while routing is unavailable. The first actual route can still wait for the engine to warm. This is an explicit remaining limitation, not a sub-second routing-startup claim.
- Public barrier submissions are paused because Vercel local SQLite storage is instance-local. A durable store, review/retraction workflow and experimental opt-in report routing remain unfinished. The local SQLite observation flow remains available.
- The study evaluates a sample of stops. A comparable countywide study and boundary-truncation filtering are not complete.
- No independent field validation, user interviews or endorsements have been performed or invented.
- Spanish and Vietnamese localization are not implemented. A basic web manifest exists; a complete offline PWA is not claimed.
- The user-supplied favicon has not arrived. No replacement favicon was invented.
- Nominatim's throttle is per process. Higher-volume multi-instance deployment needs a shared coordinator or separately hosted geocoder.
- The loaded GTFS feed exposes effective dates of October 26, 2026 through January 10, 2027. Before the start date, a missing upcoming departure can be correct; this is not real-time vehicle information.

See [methodology](METHODOLOGY.md) for assumptions and [demo](../DEMO.md) for the real two-minute flow.

## Recorded public checks

The October 20 release returned HTTP 200 for `/` and `/app` in 0.34 and 0.15 seconds in one recorded request each. These are observations, not an SLA. The same real Diridon query returned 390.1 metres for the four weighted algorithms and 753.8 metres for BFS, demonstrating its different objective. The selected wheelchair route was 20 metres longer than the standard route; its estimated time difference also included the slower assumed speed. The UI converts distances to miles.

Public address search returned real Diridon results. The official MCP client negotiated protocol 2026-07-28, discovered 13 tools and searched actual VTA stops. The production browser exercised desktop and mobile scrolling, planner, comparison, access study and the paused-reporting state with no page errors.
