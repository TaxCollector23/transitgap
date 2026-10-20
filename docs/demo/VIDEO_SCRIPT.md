# TransitGap GroundTruth demo script

Target length: about 2 minutes. Record the real deployed or local application only after its data and report storage state have been checked. Replace bracketed notes with values visible in that run.

**0:00–0:15 — The question**

“A walking route can be calculated even when details about the last few hundred meters to transit are unknown. TransitGap makes those known and unknown details easier to see.”

**0:15–0:35 — Plan a route**

Choose a real start on the map and a real VTA stop. Calculate a route. “This route follows the mapped pedestrian network. It is not an accessibility certification.”

**0:35–0:55 — Read route evidence**

Expand the route evidence section. Point out actual mapped stair, surface, barrier and crossing observations. Explain that missing tags remain unknown.

**0:55–1:20 — Compare public sources**

Turn on the City sidewalk layer and select a real candidate. Show its City and OSM provenance. “These records are spatially near each other; that does not prove they describe the same facility or current conditions.”

**1:20–1:40 — Inspect a candidate**

Open the Data Gaps list and its explanation. Read the real affected route and stop counts from that run. “The score suggests where another observation may help. It is not ridership or an official priority.”

**1:40–2:00 — Submit a report**

Select an actual map point and submit an explicitly labeled test observation. Show its `COMMUNITY_REPORTED` and `UNREVIEWED` state and reload only if the configured database is durable for that environment.

**2:00–2:15 — Close**

“TransitGap combines separately sourced map information and community observations while showing what is still unknown. More reviewed observations can make the picture more useful.”

Do not record a production report unless it is clearly labeled as a test and the maintainer approves its removal process.
