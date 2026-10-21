# Pilot methods

## Scope

The new study is bounded to a 1,500 m radius around Diridon Station. It loads actual Santa Clara County OSM walk-graph edges and actual VTA GTFS stops in that area. Its endpoint accepts one stop ID, one current mobility profile, a 1–15 minute modeled budget, and a deterministic sample size of 20–300 graph nodes.

## Toward-stop reachability

For each requested stop, the API runs shortest-time searches from the stop over the reversed directed graph. This answers whether a sampled graph origin can travel **toward** the stop; it does not reverse one-way edges or assume every edge is reciprocal. Edge weight uses existing profile cost divided by that profile’s assumed speed. Partial-edge display geometry is clipped to the remaining modeled time.

## Scenarios

- **Documented:** an edge is eligible only if it passes existing profile rules and its profile-relevant predicates are explicitly recorded.
- **Possible:** applies the same profile hard exclusions/cost model, but permits selected missing predicates. It asks what might be reachable if those unknown conditions prove usable.

Profile-relevant unknowns are deliberately limited: surface/width and unparseable directional incline on mapped pedestrian ways, smoothness for known rough surfaces, lighting for low-vision pedestrian ways, and kerb/tactile/signal evidence at mapped crossings. Unmodeled conditions remain a limitation. No missing key means a verified barrier, and no scenario guarantees a usable route.

The implementation checks `documented ⊆ possible` for all reached graph nodes and sampled origins. Origin IDs are ordered deterministically with SHA-256 and capped; this is reproducible, not representative sampling.

## Transit stop connection

Each stop is associated with its nearest graph node for analysis. If the straight-line connector exceeds 35 m, the API returns `STOP_CONNECTION_UNKNOWN` without drawing an inferred connector. Even shorter snaps are only a proximity heuristic, not confirmation of a sidewalk or curb connection.

## Interpretation

Reach counts are graph nodes in a deterministic pilot sample, not riders, residents, people, or an official statistic. OSM tags are source documentation only. Cache generation/modification timestamps are not OSM extraction timestamps; no field observation timestamp is present.

## Inspection sensitivity and sensitivity policy

The current analysis version is v2, with the original v1 SHA-256 sampling order preserved for comparison. Each selected unknown physical OSM segment is evaluated as usable versus blocked while other unknowns stay usable. A source way plus unordered endpoint pair groups both mapped directions. Candidate output includes exact changed origin/stop pairs, sample count, source URL and assumptions. Existing municipal route-proximity scores remain separately named.

`documentation_policy=width_optional_sensitivity` is a named API experiment; the default `profile_required` policy is unchanged. Only missing width ceases to exclude a documented edge; known barriers still exclude it. Missing-attribute counts make the result explainable. Neither policy is field validated.

Toward-stop edge geometry is clipped from the destination end. If documented and possible reach cover different fractions of the same directed edge, the unknown-only remainder is retained. Compact snapshots certify a conservative geometric A* lower-bound scale while loading; arbitrary input graphs use zero heuristic to preserve optimality even for nonmetric lengths. Runtime dataset graphs are treated as immutable; source edits require reloading the graph.
