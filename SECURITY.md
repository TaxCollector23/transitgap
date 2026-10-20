# Security notes

## Public interfaces

- FastAPI route and evidence endpoints validate coordinate ranges, stop IDs, limits, offsets, and bounding-box dimensions.
- Community observation submission is public, restricted to the active route area, and rate-limited in process to five reports per client address per minute. Reports are explicitly unverified.
- MCP exposes read-only search, routing, and evidence tools. It has no report submission or administrative tools. Tool inputs have length, count, and bounding-box limits.
- Streamable HTTP uses the official MCP SDK transport security with explicit allowed-host and allowed-origin configuration. The Render blueprint supplies its expected hostname. Override `MCP_ALLOWED_HOSTS` when the generated hostname differs.
- MCP request bodies are capped at 64 KiB.

## Data and persistence

No credentials are required by the checked-in application. Do not commit API keys or personal information. Community report descriptions are public; the form asks users not to submit personal details.

The SQLite report database is not durable on Vercel or the checked-in free Render configuration. Select and configure a persistent database before promising that reports will remain available.

## Remaining review

Rate limiting is process-local and is not a substitute for a shared abuse-control service. Review proxy and client-IP handling, county graph request cost, public endpoint quotas, dependency advisories, and report retention before a public release. No automated security scan or independent audit has been run for this change.
