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
