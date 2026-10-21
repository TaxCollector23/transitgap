# Accessibility limitations

TransitGap plans routes over mapped pedestrian paths and surfaces documented information. It does not certify routes as wheelchair safe, step-free, or accessible.

- Missing tags mean the information is unknown, not that an obstacle exists.
- A City sidewalk polygon documents a mapped area; it does not prove sidewalk condition, curb access, or connection to a chosen route.
- OSM and City matches use proximity. They can be false matches, especially across roads or around intersections.
- OSM and City attributes may have different meanings, dates, units, and collection methods. Differences are review candidates, not verified conflicts about real conditions.
- City records shown with `LASTUPDATE` retain the source value. It is not necessarily an inspection date. The development query found mostly 2010 update values; field currency is uncertain.
- Community submissions are public, unverified, and can be inaccurate or stale. Reports do not affect route calculations. This MVP has no review or verification workflow.
- Inspection scores rank information gathering candidates based on a deterministic sample of graph-origin routes to VTA stops. They are not pedestrian demand, ridership, government priorities, or a safety score.
- Vercel's default `/tmp` database is instance-local and may disappear on cold starts or differ across instances. A custom Vercel database path is reported as `configured-path-unverified` until its mount is confirmed durable. The current Vercel project has no such binding verified.
- No independent field validation was completed for this evaluation.

Treat all route results as planning information. Check current conditions and use personal judgment before traveling.

## How directions describe uncertainty

- Missing OpenStreetMap attributes are summarized once per route ("Some
  accessibility information is missing along this route") with the share of the
  route affected per attribute, instead of being repeated on every step. Each
  segment's missing attributes remain in the response and in "Map segments
  behind these directions".
- Documented concerns (stairs, mapped barriers, rough surfaces, steep slopes,
  raised curbs, no sidewalk) are shown on the step where they occur, labelled
  "Mapped concern", and marked on the map. They are never hidden to simplify
  the display.
- Street crossings are counted within a step, with unmarked and unrecorded
  crossing types called out.
- Straight-line connectors between a starting point or stop and the mapped
  network are shown as "Not mapped" steps and dashed lines. They are never
  phrased as a walking instruction along a path.
