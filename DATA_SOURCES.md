# TransitGap data sources

TransitGap combines separate public datasets and unverified community reports. Spatial proximity is useful for finding places to review; it does not establish that features are connected or that a route is accessible.

| Source | Use | Evidence status | Attribution and limits |
| --- | --- | --- | --- |
| U.S. Census TIGERweb county boundary | Santa Clara County supported-area outline and county graph extraction boundary | `SOURCE_DOCUMENTED` | [TIGERweb State/County service](https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer?f=pjson), county GEOID `06085`. The polygon bounds routing coverage; it does not establish complete pedestrian or sidewalk data. |
| OpenStreetMap pedestrian network | Existing OSMnx walking graph and explicit mapped pedestrian ways | `SOURCE_DOCUMENTED` | © OpenStreetMap contributors. Tags can be absent or outdated. See [OpenStreetMap copyright](https://www.openstreetmap.org/copyright). |
| City of San José Sidewalks, ArcGIS layer 185 | Sidewalk area polygons, original attributes and IDs | `SOURCE_DOCUMENTED` | [Layer metadata](https://geo.sanjoseca.gov/server/rest/services/OPN/OPN_OpenDataService/MapServer/185?f=pjson). The service describes polygon geometry and a City accuracy disclaimer. No separate open license was identified in the service item metadata; confirm reuse terms with the City before redistributing the source snapshot. |
| VTA GTFS static stops | Transit stop locations and names | `SOURCE_DOCUMENTED` | [VTA GTFS](https://gtfs.vta.org/). Static stop data does not document sidewalk access. |
| TransitGap community reports | User submitted location, category, optional text and timestamp | `COMMUNITY_REPORTED`, `UNREVIEWED` | Reports are claims and are never treated as confirmed or used to block routing. |

The City adapter reads layer capabilities and schema, requests object IDs intersecting the bounded study-area envelope, batches those IDs below the service record limit, requests WGS84 GeoJSON, and preserves source IDs and attributes. It caches a timestamped snapshot. The analytical index clips City polygons to the circular 1,500 m Diridon pilot area. This remains the only municipal sidewalk source currently integrated; other county cities are not represented. It and reprojects geometries to EPSG:26910 for distances. A source retrieval timestamp is not a field inspection date.

Matching uses explicit OSM pedestrian-path classes, not road centerlines. The current 5 m correspondence threshold and 14 m review threshold are in meters. A match means proximity only. Distinct nearby paths, offset ambiguity, and source disagreement should prompt review. OSM and City source geometries remain separate in API results.

The City public service was queried during development. Its metadata reported a 2,000-feature maximum response count and query support. A bounded envelope query returned 1,829 GeoJSON features while the service count response was 1,828; this discrepancy was not reconciled and is not an evaluation result. The deployment build packages a bounded snapshot when the service is available. Runtime startup uses the packaged/cache snapshot without waiting on the municipal network; without a snapshot, the source is marked unavailable.

San José road closures are not integrated because a road closure does not establish a sidewalk closure. Project Sidewalk and Panoramax were not integrated: no local, license-reviewed coverage result was established for this release. No outside-city observations or imagery are substituted.

## Stations, platforms, entrances and schedule validity

- Only boarding locations (GTFS `location_type` 0 or empty) are offered as
  destinations. Parent stations (1), entrances (2) and generic nodes (3) are
  attached to their platforms instead of being listed as separate stops. In the
  October 2026 VTA feed this removed 114 non-boarding records (73 stations, 35
  entrances, 6 nodes) that previously appeared as duplicate stops.
- A platform's empty or `0` `wheelchair_boarding` inherits its parent station's
  value, as the GTFS reference specifies. A value of `0` everywhere stays
  "not recorded"; it is never shown as accessible.
- When a station has entrances in its feed (BART Milpitas and Berryessa, the
  Caltrain Diridon elevator, several VTA light rail stations), walking routes
  end at the best reachable recorded entrance instead of drawing an unmapped
  straight line to a platform coordinate. Wheelchair and stroller routes use
  entrances the feed marks step-free when it records that, and never use an
  entrance marked not step-free. The route inside the station is not modeled.
- Scheduled departures are shown only when today falls inside the publisher's
  `feed_info` start/end dates (or the calendar range if `feed_info` has none).
  As checked on 2026-10-20, BART's official permalink feed declares an end date
  of 2026-08-30 even though its calendar runs into 2027, and VTA's current feed
  starts 2026-10-26. TransitGap therefore shows routes but withholds departure
  times for both, with a link to the agency, rather than presenting them as
  current. No live/real-time source is connected.
