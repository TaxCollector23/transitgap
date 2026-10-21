# First-time participant usability test

An unassisted, task-based session for someone who has never used TransitGap.
Automated browser tests show that controls work; they do not show that people
understand them. Run this before claiming the interface is intuitive.

## Who to recruit

Aim for 5 participants per round, at least one from each group:

- Uses a wheelchair, mobility scooter or stroller day to day.
- Uses a screen reader (VoiceOver on iPhone or NVDA/JAWS on Windows).
- Has low vision and uses zoom or high contrast.
- Rides VTA, Caltrain or BART but has never heard of TransitGap.

Do not recruit TransitGap contributors or people who have seen a demo.
Offer fair compensation and get informed consent. Record only what the
participant agrees to; do not record faces or exact home locations.

## Setup

- Their own phone and browser if possible, otherwise a 390×844 phone and a
  laptop at 1440×900 with their usual assistive technology.
- Open `https://transitgap.vercel.app/app` directly. Do not show the landing
  page or explain the app.
- The facilitator reads tasks aloud and does not demonstrate, hint or point.
  If a participant asks "what do I do?", answer "What would you try?".
  Stop a task after 4 minutes and mark it not completed.

## Tasks

Read each task exactly as written. Use a nearby origin the participant knows
when possible; the fallback origins below are public places.

1. "Without touching anything yet: what do you think this page is for, and
   what would you do first?" (first 5 seconds; record their words)
2. "You're at San Jose City Hall. Find a walking route to the Diridon
   Caltrain station."
3. "You use a wheelchair. Change the route so it fits how you travel."
4. "Tell me how you'd get there, in your own words, from this screen."
5. "Is there anything about this route you'd want to know before going?"
   (watch whether they find and correctly interpret the missing-information
   message; record misreadings such as "unknown means it's fine")
6. "You don't know the name of any stop near Santa Clara University. Find a
   BART or Caltrain station you could walk to."
7. "You saw a broken curb ramp yesterday on The Alameda. Tell TransitGap
   about it." (stop before Submit on the public site; reports are real data)
8. "Where would you look to see which stops are hardest to reach in a
   wheelchair?"
9. Screen reader and keyboard participants only: repeat task 2 without the
   map or a mouse.

## What to record per task

| Measure | How |
| --- | --- |
| Completed unaided | yes / with confusion / no |
| Time to complete | seconds from end of the task prompt |
| Interactions | taps, clicks, swipes or key presses, counted from the recording |
| Wrong turns | controls tried that did not help, verbatim |
| Misunderstandings | especially about "missing information", "not mapped" connectors, stations versus platforms, and scheduled versus live times |
| Confidence | "How sure are you this route works for you?" 1–5 |

After all tasks ask: "What, if anything, was confusing?" and "What would
you change first?" Record their words, not a paraphrase.

## Reporting

Report raw counts per task (for example "4 of 5 completed task 3 unaided").
Do not average across participants with different assistive technology, do
not convert results into a score, and do not report a task as passed when
the facilitator helped. File each confusion as an issue with the participant's
words and the screen it happened on.
