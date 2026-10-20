# TransitGap methods

TransitGap measures modelled pedestrian access to published VTA stops. It does not certify routes, replace a field inspection, estimate disabled populations, or present static schedules as live arrivals.

## Data and geographic scope

- Pedestrian paths: OpenStreetMap, acquired through OSMnx's walk filter. The county cache was built from the official Geofabrik Northern California extract and clipped to U.S. Census Santa Clara County GEOID 06085.
- Transit: the official VTA GTFS archive. The prepared county graph has 291,569 nodes, 811,314 directed edges and 3,348 stops connected within 150 metres of a graph node. These are dataset counts, not accessibility claims.
- Municipal evidence: City of San José sidewalk polygons within the 1,500 metre Diridon pilot. Proximity to a path is not proof that two records describe the same facility.
- Community reports: unreviewed observations. Production submissions are paused while storage is instance-local. Reports never silently block a route.

Sources: [OpenStreetMap attribution](https://www.openstreetmap.org/copyright), [Geofabrik](https://download.geofabrik.de/north-america/us/california/norcal.html), [VTA GTFS](https://gtfs.vta.org/gtfs_vta.zip), [GTFS specification](https://gtfs.org/documentation/schedule/reference/), [City sidewalk service](https://geo.sanjoseca.gov/server/rest/services/OPN/OPN_OpenDataService/MapServer/185).

## Routing and mobility profiles

The network is a directed multigraph. Every selected parallel edge retains its identity, length and ordered geometry. Endpoint connectors are straight-line approximations and are explicitly unassessed. Origin snapping uses a cached spherical KD-tree, with a 120 metre maximum snap. All connected components are preserved; a nearby isolated path is not silently replaced by a distant largest component.

Standard routing minimizes mapped distance. Wheelchair and stroller profiles exclude mapped steps, wheelchair prohibitions, raised crossing kerbs and restrictive barriers. They penalize rough surfaces, poor smoothness and measured slopes above 8%. Stroller and wheelchair surface preferences differ. Low-vision preferences use recorded tactile paving, signals, audible signals and lighting where these attributes survive in the cache.

The thresholds and multipliers are inspectable in `backend/app/profiles.py`. They are modelling choices, not a universal description of user needs. The 8% slope concern is close to, but not a compliance test for, the [ADA 1:12 ramp limit](https://www.access-board.gov/ada/guides/chapter-4-ramps-and-curb-ramps/). `incline=up/down` records direction, not a measured grade. Node surface information is not extrapolated across an entire edge.

Costs stay at or above physical length. Positive documentation removes uncertainty penalties rather than creating below-distance bonuses, preserving the geographic lower bound used by A*. Dijkstra, bidirectional Dijkstra, A* and queue-based Bellman-Ford minimize the same profile-weighted cost. Breadth-first search minimizes eligible network segments and can produce a longer walk. Searches have a three-second search budget checked periodically.

## Evidence along a route

Segments are **mapped**, **unknown**, or a **mapped concern**. None is labelled field-checked without an actual reviewed observation. Unknown segments use a dashed line; concern segments also have explicit textual reasons. The coverage fraction is the length-weighted share of applicable attributes documented in OpenStreetMap. It is not the probability of access or the proportion independently verified.

Missing slope, surface, width or crossing records remain unknown. Existing caches may omit tags that were not retained during acquisition. Adding a tag to the acquisition allowlist cannot recover it from an older cache. Simplified graph nodes also do not preserve every original intermediate-node condition. These are limits of the model, not proof that a physical feature is absent.

Directions are generated from the selected edges, their stored names and bearings. Unnamed paths remain unnamed. Connectors are identified as unassessed. Missing information and mapped concerns accompany the relevant instruction.

## Mobility detour

`POST /compare` computes the standard and selected-profile route for the same origin and stop using A*. It returns distance and time differences. Assumed speeds are 1.2 metres per second for standard and low vision, and 0.9 for wheelchair and stroller. The time difference includes those different assumptions. If no alternative exists in the graph, the detour is unavailable, never fabricated or replaced with zero.

## Ten-minute access study

The build evaluates 32 stops selected at evenly spaced positions in a latitude/longitude-sorted list of real county stops. This is a reproducible spatial sample, not a statistically representative county study or a countywide worst-stop ranking. Additional selected stops can be evaluated on request.

For each stop, reverse Dijkstra measures travel **toward** the stop within 600 seconds. Edge budgets include the same profile costs and assumed speeds used by routing. Reachable edge fragments at the cutoff are retained. Reciprocal geometry is deduplicated, and reachable intervals from both ends are merged before measuring physical network length.

`gap = 1 - wheelchair_reachable_length / standard_reachable_length`

A zero standard denominator produces an unavailable score. The different speeds and profile penalties both affect the result; the score does not isolate infrastructure barriers from modelling assumptions. A large gap is a reason to examine the inputs, not a finding that a place is inaccessible.

The API includes the reachable line network and a five-metre buffered display polygon. Polygon area is not the gap metric. The graph ends at the county boundary, so nearby walksheds can be truncated. Rankings compare only evaluated stops and must be read with those limitations.

## Schedules

The parser streams `stop_times.txt`, retains loaded stops, joins trips and routes, and evaluates weekly calendars plus date exceptions in America/Los_Angeles. Previous-day service covers GTFS times above 24:00. Departures are scheduled, not real-time. The loaded feed's effective dates are exposed; an out-of-range date can correctly produce no upcoming departure. GTFS boarding status is separate from the pedestrian approach: 0 unknown, 1 accessible boarding recorded, 2 inaccessible boarding recorded.

## Civic follow-through and privacy

Letters contain actual stop and model results, named sources and limitations. They are editable downloads and are never automatically sent. No agency response is claimed.

Address search is explicit rather than autocomplete. A backend proxy bounds queries geographically, uses an identifying User-Agent, throttles outbound requests to one per second per process and keeps a bounded ten-minute memory cache. Text is sent to Nominatim only when the user submits it. Coordinates and addresses are not stored in browser preferences by default. Sharing a journey deliberately places its origin in the URL. Multi-instance geocoder scaling requires a shared rate coordinator or a separately hosted provider.

## Verification still needed

Automated graph, protocol, browser and accessibility checks cannot establish real-world usability. No field routes, interviews, endorsements or accessibility certifications have been invented. Field checks, durable report storage and a representative larger study remain necessary before making broader conclusions.
