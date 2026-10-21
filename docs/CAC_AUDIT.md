# TransitGap CAC audit

Audit date: October 20, 2026. Checkout: `codex/mobility-refinement`.

## Product and data inspected

- The existing React/MapLibre landing page is `/`; the planner is `/app`. The current UI retains route, stop, evidence, access-gap, and report flows.
- FastAPI loads a directed NetworkX multigraph from the Santa Clara County OSM pedestrian extract and actual VTA GTFS. County graph manifest: 291,569 nodes / 811,314 directed edges; OSM acquisition snapshot date is not recorded. GTFS version `2026-10-09_14:57`, effective 2026-10-26 through 2027-01-10.
- Existing route algorithms are Dijkstra, bidirectional Dijkstra, A*, Bellman-Ford, and breadth-first. Profiles include standard, wheelchair, stroller, low vision, and prefer documented paths.
- The prior gap study compares standard and wheelchair modeled walking-network reach. New bounded Diridon analysis compares source-documented with possible reach toward actual GTFS stops. It is not field verification or an accessible-route guarantee.
- Public reports remain disabled without durable storage. The prior Render database attempt required billing; no card was supplied. No durable database is configured.

## P0 defects and fixes in this sprint

1. Added `/accessibility/reachability/stops` and `/accessibility/reachability/{stop_id}` for actual GTFS stops in a 1,500 m Diridon pilot. Computes directed reverse walksheds toward stops, explicit connector uncertainty, source-linked unknown OSM tags, deterministic node samples, selectable GeoJSON overlays, and a text explanation.
2. Corrected outdated browser assertions and an ambiguous dropdown selector. The full local real-data browser suite passes after the selector correction.
3. Added loading and empty-state behavior for sampled access-gap summaries. Preserved the landing and map visual design.
4. Added reproducible student algorithm implementation tasks and tests without implementing that student-owned algorithm.

## Known limitations

- The possible scenario retains existing profile hard exclusions and treats only the listed missing predicates as unknown. The documented scenario excludes edges missing those predicates. This is an explicit model, not proof of physical usability.
- The deterministic origin sample is not population weighted. GTFS stop snapping is nearest-node distance, not verified sidewalk/curb connectivity; connections over 35 m are reported unknown.
- OSM cache modification/generation time is distinct from missing OSM source snapshot date and missing field observation time.
- No human field observations or consented usability sessions are recorded. No CAC registration/submission receipt or demo video is recorded.
- National CAC materials currently conflict with the CA-17 page on deadline. Confirm directly with the portal or office.

See [CAC_RELEASE_STATUS.md](CAC_RELEASE_STATUS.md) for current gate state and exact check results.
