# Browser QA — October 19, 2026

The built-in browser was used for visible interaction checks against the existing production site and the current Vite preview at `http://localhost:5173`. Desktop layout was checked at 1280 × 800 and the mobile layout at the browser's approximately 507 × 804 default viewport. This is a manual browser record, not a claim that the Playwright suite passed.

## Passed in the current frontend preview

- Open the landing page, follow **Plan a walk**, and refresh `/app` directly.
- Observe the map loader and its removal after the map and route data become ready.
- Select A on the map, search for Diridon, select B, and calculate a route.
- Display the route as **0.10 mi**, **2 min**, and an assumed speed of **2.7 mph**.
- Change A and calculate another route; B remains independently selectable.
- Display network-distance warnings in miles after correcting the metric error messages.
- Enter report-pin mode, cancel with Escape, then click the map without placing a stale report pin.
- Collapse the mobile planner during start placement, then reopen it after the point is chosen. This was fixed after the initial mobile check found that the sheet obscured the map.
- Reset clears A, B, route details, and the route geometry and disables route calculation until inputs are chosen again.
- When evidence endpoints fail, show community reports as unavailable with an unknown count, rather than displaying zero reports. Provide an evidence retry action.

Screenshots of a completed desktop and mobile route were saved as local review artifacts.

## Runtime and release limits

The currently running local backend is the earlier Diridon implementation: `/coverage` returns a 1,500 m radius and `/data-sources` returns 404. Therefore these checks verify current frontend interactions with the existing route service, not the new county backend, municipal comparisons, report persistence, or MCP transport.

Reloading `https://transitgap.vercel.app/` still showed the Phase 1 UI with 99 stops and a kilometer result. A production route was calculated successfully, but the new source changes have not been deployed.

Terminal commands, including `git status --short --branch` and `vercel --version`, were denied before execution because the local Trace hook could not reach its service. The Trace hook remains enabled. County graph preparation, the full build, backend tests, commit, push, and deployment are waiting for that service to be restored.
