# Map startup correction — October 20, 2026

The previous public build downloaded tiles and reported readiness but could render
an empty map. Its late MapLibre stylesheet overrode `.map { position:absolute }`
with `position:relative`. The map container measured **zero height** on fresh
1440×900 and 390×844 production visits; its 300px default canvas was clipped.
Earlier canvas-visibility checks did not detect the clipping parent.

The map now has a more specific, explicitly viewport-sized layout. Its code is
part of the planner import, removing a nested dynamic-import round trip. Prepared
stop data starts loading alongside that bundle and shares one request. Initial
county fitting has no intermediate animation. Cluster labels use local fonts
instead of a demo glyph endpoint that returned HTTP 404.

On a fresh browser context with 150ms network latency, 5Mbps download and 4× CPU
throttling, the local production build with real OSM tiles measured:

| Viewport | Canvas present | Initial tiles ready | Actual map height |
|---|---:|---:|---:|
| 1440×900 | 2.092s | 3.027s | 900px |
| 390×844 | 2.063s | 2.582s | 844px |

These are single synthetic runs, not population performance percentiles or a
claim that public tile delivery is guaranteed. Screenshots were visually checked.

Two new production-build browser regressions check container and canvas size,
point selection, one bootstrap request and zero remote glyph requests while
holding the backend health request indefinitely. Raster responses in those
regressions are deterministic fixtures. CI now executes these checks after the
existing reporting/browser fixture suite. Real OSM rendering was checked
separately; it is not inferred from fixture images.

The county routing service still has its previously measured cold initialization
cost. This frontend correction does not claim to remove that backend cost; map
exploration and choosing a journey are independent of it.
