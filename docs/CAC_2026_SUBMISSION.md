# CAC submission and human validation

Official pages checked October 20, 2026 (Pacific). The national registration page
currently says **October 26, 2026, 9 pm ET (6 pm Pacific)**:
https://www.congressionalappchallenge.us/students/student-registration/ .
The linked May rulebook instead says October 26 at noon EDT:
https://www.congressionalappchallenge.us/wp-content/uploads/2026/05/2026-CAC-Rules.pdf .
The indexed Khanna district page lists October 30, 11:59 pm EST:
https://khanna.house.gov/services/congressional-app-challenge . Direct district
page access returned 403 during this audit. These official sources conflict.
Use October 26 at noon Eastern (9 am Pacific) as the conservative planning cutoff
and confirm the live submission portal/district office deadline. No application
or deadline extension has been verified, and no message was sent to the office.

National rules require middle/high school status at submission, U.S. residence,
district eligibility by home or school, and at most four team members (at least
half district-eligible). Confirm these personally; the repository cannot establish
eligibility. A public 1–3 minute YouTube/Vimeo demonstration should name the actual
participants and app, describe purpose and audience, name languages/tools and
show functioning behavior. Answer the portal's actual inspiration, technical
challenge, learning and future-development questions in your own words. Check
the portal's AI disclosure questions and disclose the assistance recorded in
`AI_ASSISTANCE.md`. Do not claim AI-generated code as independently authored.

## Reproducible 2:40 demo draft

- 0:00–0:15: actual student name and TransitGap. “TransitGap helps people examine
  walking access to public transit and the accessibility information behind it.”
- 0:15–0:45: open `/app`, use coordinates 37.32875, -121.90442, choose San Jose
  Diridon (Bay 11), select Walking, Find route. Show distance, time and A/B line.
- 0:45–1:10: change to Wheelchair and use the comparison control. Report the actual
  measured detour or same-path result on screen; do not promise a different route.
- 1:10–1:35: open Accessibility details. Explain one recorded concern and one
  unknown attribute. Unknown is not proof of an accessible or blocked sidewalk.
- 1:35–2:00: open the Diridon missing-information study, choose stop 4514 if
  available and show the seeded inspection result. Explain that the count is
  hypothetical sampled graph journeys, not people or a municipal grade.
- 2:00–2:25: show the genuine student reference implementation, tests and measured
  result ONLY after the student has completed it. Until then this segment is blocked.
- 2:25–2:40: explain Python/NetworkX, React/TypeScript, MapLibre and official data;
  name AI assistance and the lack of physical route certification.

Source explanation: keyed directed OSM edges retain geometry and accessibility
attributes. Profiles constrain/penalize those edges. A* uses a checked lower
bound; reverse searches model travel toward stops. Documentation scenarios are
explicit assumptions. Station entrances come from agency GTFS; station interiors
are not modeled. Expired/not-yet-valid feeds provide no supposedly current times.
The demonstrated technical challenge can be startup profiling and lossless graph
loading, but describe the student's actual debugging/design contribution honestly.

## Unassisted session (15 minutes; no participant data invented)

Ask permission to record task outcomes anonymously. Give no interface coaching:
1. Find a walking trip from the supplied starting point to a VTA stop.
2. Change the same trip to Wheelchair. Explain what changed and what remains unknown.
3. Find Santa Clara Caltrain, then Berryessa/North San José BART. Explain where the
   route ends and whether the shown departure information is current.
4. Collapse/expand the mobile planner, change the origin using the keyboard only,
   and find a route. Repeat with the participant's normal screen reader.
5. On the isolated test site, submit a clearly synthetic construction report and
   explain its verification status. Do not publish a made-up production report.

For each task record success without help, time, actual click/keypress count,
wrong turns, words of confusion, assistance requested, and optional verbatim
feedback with consent. Ask what route information they trusted and why. Use
390x844, 768x1024, 1440x900 and 1920x1080 as relevant. Axe/Playwright validate
specific technical properties; they do not establish human usability. Real
screen-reader use, participants and physical checks are still human tasks.

## Submission checklist

- Confirm eligibility and district participation in the portal.
- Complete the independent student task and honest contribution record.
- Visit selected field candidates using FIELD_CHECK_SHORTLIST.csv; date actual
  observations and retain disagreements. No physical observation is prefilled.
- Run actual participant sessions and record outcomes; leave unperformed tasks blank.
- Record a public 1–3 minute video with real measured behavior and authorship.
- Complete portal questions, AI disclosure and guardian/participant requirements.
- Submit before the confirmed deadline and retain the actual receipt.

Engineering validation and contest submission are separate. A deployed app is not
a completed submission. Human validation, independent authorship and a receipt
are not established by automated tests.
