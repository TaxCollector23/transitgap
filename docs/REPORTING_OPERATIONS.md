# Durable reporting operations

Production uses an isolated `transitgap` database in an existing Neon Free
project. No paid project or subscription was created. Runtime credentials belong
to an ordinary PostgreSQL role with no schema CREATE, report DELETE or review
history UPDATE/DELETE permission. The database owner applies migrations separately.

Set `DATABASE_URL` to the runtime pooled PostgreSQL URL,
`TRANSITGAP_REPORTS_MIGRATED=1`, `TRANSITGAP_MODERATION_TOKEN` and
`TRANSITGAP_REPORT_RATE_SECRET` (independent random secrets of at least 32
characters). Credentials live in Vercel's sensitive production environment;
local operator exports are in the ignored `.env.reporting.local` file, mode 0600.
Never commit that file, share its contents, or expose these as `VITE_*` variables.

The owner runs `python scripts/migrate_reports.py` with an owner DATABASE_URL and
without TRANSITGAP_REPORTS_MIGRATED. Migration 001 preserves reports and append-only
reviews; 002 adds unique submission keys and shared rate limits. Migrations are
transactional with a PostgreSQL advisory lock. Do not initialize production with
SQLite or the test-database URL. Health must show `postgresql` and reports enabled.

Public reports are unverified claims. Five requests per minute bucket are allowed
per keyed client fingerprint across instances. Raw IPs are not stored. Vercel's
trusted forwarding header identifies clients; old hash buckets are removed on
the next submission after two minutes. This is basic abuse prevention, not proof
of a human or protection from distributed botnets. Descriptions have bounded
length, reject control characters and redact common email/phone patterns. Users
should avoid names, contact details and other personal information. Geographic
coordinates and descriptions are public. There is no user-account/contact data.

The frontend assigns a UUID Idempotency-Key and retains it across an ambiguous
network failure. The database confirms an insert before returning success. An
identical retry returns the same report; a different payload with the same key
returns 409. Storage errors never produce a success message.

## Review

Source your private operator environment locally, then run
`backend/.venv/bin/python scripts/moderate_reports.py` to list all reports,
including rejected/outdated records. Review with `--id ID --status UNDER_REVIEW
--reviewer ALIAS --reason 'Evidence and next steps'`. Use REVIEWED, REJECTED or
OUTDATED as appropriate. Every transition appends history under a row lock.

Effects require REVIEWED status, an explicit `[u,v,key]` mapped edge within 35 m,
supported category/profile relationship, and an expiry within 30 days. Use
`--edge JSON --effect block --profiles wheelchair stroller --until ISO_TIMESTAMP`
only after a human has established the physical association. To revoke an effect,
review again with `--effect none`, or mark the report OUTDATED/REJECTED. The next
route reads current effects once for all station entrances; no stale effect cache
is used. Unverified reports never change route weights.

Do not submit synthetic reports to the public dataset. Tests use separate
PostgreSQL schemas inside a database whose name ends `_test` and destroy only
those test schemas. Run `TRANSITGAP_TEST_DATABASE_URL=postgresql:///transitgap_sprint_test
backend/.venv/bin/python -m pytest backend/tests/test_postgres_reporting.py -q`.
Set the same test variable when running the fixture Playwright suite to exercise
the mobile form against PostgreSQL. A database outage deliberately blocks routing
when reviewed effects cannot be checked, rather than silently ignoring an active
reviewed barrier. Neon availability, quotas and backups remain provider limits.
