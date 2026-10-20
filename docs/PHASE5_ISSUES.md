# Phase 5 issue register

## Open

### P1 — County build and county route behavior are unverified

The deployment preparation script now requests an OSM walking graph for the Census Santa Clara County polygon and filters the VTA feed to that polygon. The graph has not been acquired or measured. Memory, build duration, routing latency, package size, route connectivity, and Vercel function limits remain unknown.

### P1 — Municipal sidewalk evidence is not countywide

The integrated municipal source is the City of San Jose sidewalk layer and the cached comparison snapshot remains within 1,500 m of Diridon Station. County routes and VTA stops do not make this source cover other cities. Countywide evidence requires reviewed sources and coverage metadata for each municipality.

### P1 — Community report storage is ephemeral on current deployment targets

The existing report store is local SQLite. Vercel filesystems and the Render blueprint's free instance are ephemeral. Reports may disappear after instance replacement or restart. Do not describe the current configuration as durable production reporting.

### P1 — Release validation, commit, push, and deployment are blocked

The local pre-tool hook rejected terminal commands before execution with `Trace could not check this action: fetch failed`. Repository status, branch divergence, build output, credentials, and deployment state could not be confirmed. No commit, push, or deployment is claimed.

### P1 — MCP Streamable HTTP is not protocol-tested

The nine read-only tools and official SDK integration are present in source, with an in-process SDK test and an HTTP smoke script. Neither has run. Host allowlists and the Render hostname must be confirmed against the deployed service.

## Frontend changes

Manual checks for selection, mile display, error units, mobile sheet behavior, and reset are recorded in [BROWSER_QA.md](BROWSER_QA.md). The active backend is the earlier Diridon version; county and evidence runtime validation is still open.

- Origin-pick clicks now take precedence over stop and evidence markers.
- A single `idle | origin | report` mode prevents stale report placement after Escape, cancel, reset, or choosing a route stop.
- The interface labels A, B, and R and explains that B is an actual VTA stop.
- Report point is cleared after a successful submission.
- Root landing and direct `/app` route fallback are implemented.
- Displayed distances and walking speed are converted to miles.
- A loading indicator remains until the map style and API data are ready.

## P2 — Accessibility and visual QA evidence is incomplete

The Phase 5 UI changes have not been inspected at mobile sizes, run through axe, or manually checked with keyboard and screen reader tooling.
