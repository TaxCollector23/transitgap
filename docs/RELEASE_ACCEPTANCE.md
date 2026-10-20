# Release acceptance matrix

Final hosted verification is in progress. This file will be updated with actual deployment/CI evidence before the sprint is reported complete.

| Gate | Evidence so far | State |
|---|---|---|
| Git / CI | PR #8 open; ddb1285 required checks passed; final code checks pending | Pending final head |
| Backend | 131 unit/integration/contract tests pass locally | Pass |
| Routing | Five algorithms tested; profile constraints and A* counterexample covered; BFS explicitly uses hops | Pass locally |
| Reachability | Pinned graph evaluation at 3 actual stops; source-linked missing fields and width sensitivity | Pass locally |
| Inspection metric | 29 initial contract/independent cases; real API/UI integration and bounded candidate selection | Pass locally |
| Frontend | 11 real-data local browser tests | Pass locally |
| Accessibility | Keyboard routes, axe and synthetic local-speech controls pass | Pass automated; real assistive-technology validation outstanding |
| Mobile | 390×844 route flow; landing checks at 375, 390, 768, 1440, 1920 widths | Pass locally |
| Data | Actual OSM/VTA, graph hash in benchmark; unknown snapshot/observation dates retained | Pass |
| Reporting | Fixture storage persists across reload; public reports stay disabled without durable storage | Pass for configured behavior |
| Deployment | New hosted release / external smoke and browser checks pending | Pending |
| CAC submission | Student contribution, field/user work, video, deadline confirmation and receipt not provided | Awaiting human work |
