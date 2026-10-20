# A city for all

Landing page only: `frontend/src/LandingPage.tsx`, `frontend/src/landing.css`, and the no-JavaScript heading in `frontend/index.html`. Routing application, backend, and MCP are unchanged.

## Artwork

User-supplied park image restored with built-in imagegen in **edit mode**. Original: 758 × 428. Generated output: **1672 × 941** (the tool did not return the requested 3840 × 2160; this is not a 4K asset).

- PNG master: `frontend/public/images/city-for-all.png`
- Website: `frontend/public/images/city-for-all.webp`, losslessly encoded with `cwebp -lossless`; approximately 846 KiB versus 1.3 MiB PNG.
- Rendered with deliberate pixel edges, responsive cropping, fixed image dimensions, and high fetch priority. Artwork is limited to the first viewport.

Exact imagegen prompt:

> Edit target: the supplied pixel-art city park image. Upscale and carefully restore it as a high-resolution 3840 by 2160 landscape website hero background. Preserve the original composition and artwork as closely as possible: the same blue and pale turquoise sky, blocky white clouds, green park trees at left and right, open branching pale walking paths and lawn, blue/lavender city skyline in the middle distance, peaceful bright daylight. Preserve a deliberate crisp pixel-art grid and hard stepped edges, clean flat color regions, and the existing palette. Remove low-resolution screenshot softness and compression artifacts. Do not make it photorealistic, painterly, smooth-vector or blurry. Do not add people, text, logos, new buildings, or objects. Keep the sky spacious and the paths and tree silhouettes faithful. This is a faithful upscale/restoration, not a redesign.

## Visual review

Before screenshots: desktop 1440 × 900 and phone 390 × 844.

First review: checked full desktop and mobile pages, then increased navigation targets to 44px and made editorial source links explicitly underlined.

Second review: checked tablet 768 × 1024 and phone 375 × 812 hero crops, then increased footer link targets to 44px. Navigation remains visible on mobile without a hidden menu. The white overlay is limited to the hero and preserves readable black text.

Final checks cover five requested viewport sizes, normal scrolling, two hero CTAs, anchor navigation, reduced motion, keyboard access, font preservation, image loading, black text, white editorial sections, no horizontal overflow, map entry and refresh, browser back, existing real routes, and automated accessibility checks. Screenshots are generated under `frontend/test-artifacts/screenshots/` (ignored local artifacts).

The landing page does not load MapLibre. Its existing route-engine warmup is preserved. Source descriptions retain the county-wide VTA scope and distinguish the Diridon municipal-data pilot from county coverage. No route is described as independently verified.
