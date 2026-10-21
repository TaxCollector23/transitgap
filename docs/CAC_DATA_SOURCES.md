# Data sources and provenance

| Source | Use | Version / time | Limits |
|---|---|---|---|
| [OpenStreetMap via Geofabrik Northern California](https://download.geofabrik.de/north-america/us/california/norcal-latest.osm.pbf) | County walking graph and OSM way evidence | Cache has 291,569 nodes and 811,314 directed edges; cache modified / manifest generated 2026-10-20. Source snapshot date not recorded. | Tags can be missing or stale; not a field audit. The manifest date does not establish acquisition date. |
| [VTA GTFS static feed](https://gtfs.vta.org/gtfs_vta.zip) | Transit stops and feed provenance | `2026-10-09_14:57`; effective 2026-10-26 to 2027-01-10 | Static schedule; not live operations, sidewalk access, or curb connection. |
| [U.S. Census TIGER/Line county boundary](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html) | Santa Clara County clipping boundary | See data manifest for local source metadata | Boundary is for analysis extent, not a mobility-accessibility claim. |
| City of San José sidewalk GIS | Existing local comparison context | Existing cache/source manifest | Polygon proximity does not prove topology, ramps, continuity, or accessibility. |

The pilot result links specific OSM way records from its API response. For example: [way 25902649](https://www.openstreetmap.org/way/25902649), [way 25902647](https://www.openstreetmap.org/way/25902647). No field observations are stored in this release.
