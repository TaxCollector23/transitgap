# Transit agency feeds

TransitGap includes VTA bus stops and rail platforms from the published Caltrain
and BART GTFS schedule feeds. Feeds are fetched during deployment builds, filtered
to Santa Clara County, and joined to the same OpenStreetMap walking graph. Only
boarding platforms are shown; parent stations and entrance records are excluded.
Platform locations must snap within 150 metres of a mapped walking-network node.

Search results, map markers, stop details, `/stops`, `/route`, and the TransitGap
MCP stop search include all three agencies. Rail IDs are namespaced (`caltrain:`
and `bart:`) to keep them distinct from VTA IDs. Access-gap and ten-minute
reachability analyses still use VTA stops only; those analyses are not applied
to rail platforms. Rail data describes scheduled stops and departures, not
real-time service or verified step-free access.

The Caltrain feed covers 2026-01-31 through 2027-01-31. The currently published
BART snapshot lists service only through 2026-08-30. Its station locations remain
useful, but TransitGap labels its timetable expired and links to BART for current
times. These dates come from each feed's `feed_info.txt` and are not manually
assumed to be current.

Sources and terms: [VTA developer data](https://www.vta.org/go/developers),
[Caltrain developer resources and license](https://www.caltrain.com/developer-resources),
[BART GTFS schedules and developer license](https://www.bart.gov/schedules/developers/gtfs).
No agency logo or system map is used.
