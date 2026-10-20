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
| Planner performance | Route features memoized; typing no longer refits the map. Municipal evidence loads only when opened. MapLibre now downloads separately from the 28.47 KB planner chunk. |
| Sharing | Explicit origin/stop/profile journey links; no automatic home-location storage. |
| MCP | Existing public server committed and pushed in `a479865`; 13 read-only tools now implemented locally. Official-client HTTP, in-memory and stdio paths exercised. |
| Browser verification | Eight passing Playwright checks, including automated WCAG A/AA checks on landing, planner and gap views. Automated checks are not a full accessibility certification. |
| Backend verification | 65 passing pytest tests, including the final evidence snapshot roundtrip and source invalidation check. |
| Production build | Passes after MapLibre splitting. Remaining large chunk is the lazy map renderer. |

## Open work and limits

- Final commit, push and production verification are in progress. The broken Trace integration was removed by the user and terminal access is restored.
- The immutable municipal-evidence snapshot passes its regression test. The local county API initialized in 10.492 seconds in the recorded run; this is not a production latency promise.
- Public barrier submissions are paused because Vercel local SQLite storage is instance-local. A durable store, review/retraction workflow and experimental opt-in report routing remain unfinished. The local SQLite observation flow remains available.
- The study evaluates a sample of stops. A comparable countywide study and boundary-truncation filtering are not complete.
- No independent field validation, user interviews or endorsements have been performed or invented.
- Spanish and Vietnamese localization are not implemented. A basic web manifest exists; a complete offline PWA is not claimed.
- The user-supplied favicon has not arrived. No replacement favicon was invented.
- Nominatim's throttle is per process. Higher-volume multi-instance deployment needs a shared coordinator or separately hosted geocoder.
- The loaded GTFS feed exposes effective dates of October 26, 2026 through January 10, 2027. Before the start date, a missing upcoming departure can be correct; this is not real-time vehicle information.

See [methodology](METHODOLOGY.md) for assumptions and [demo](../DEMO.md) for the real two-minute flow.
