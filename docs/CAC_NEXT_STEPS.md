# Congressional App Challenge: next steps

Research date: October 20, 2026. These are AI-assisted planning notes, not claims of completed features, field validation, or student authorship.

## Official guidance

The CA-17 office page lists idea quality/originality, implementation/user experience/design, and coding/programming excellence. District judges review the demo and submission answers and may request the working app and source.

- [Ro Khanna's district guidance](https://khanna.house.gov/services/congressional-app-challenge)
- [National 2026 rulebook](https://www.congressionalappchallenge.us/wp-content/uploads/2026/05/2026-CAC-Rules.pdf)
- [National rules page](https://www.congressionalappchallenge.us/students/rules/)

The national rulebook allows AI assistance with full disclosure, substantial student contributions, and technical understanding. Prepare an accurate account of the student's work, libraries, and AI assistance. Do not describe AI-written code as unassisted student work.

**Deadline conflict:** the national rules page and rulebook say October 26; the office page says October 30. Even national sources differ on the hour. Confirm the exact deadline with the office/registration portal and plan to finish before October 26. No office contact or registration submission has been made.

## Highest-value product addition: repair-impact simulation

Proposed: select a documented barrier, simulate a stated improvement, and recompute mobility access before and after. Report changes in route distance (miles), journey time, and reachable VTA stops. Preserve the unchanged baseline graph; apply the scenario to a copy or temporary overlay. Keep unobserved attributes unknown. Present every output as an assumption-based simulation, with the affected edge and source evidence inspectable.

This builds on the actual graph and evidence system and gives a short demo a clear chain: barrier → detour → proposed improvement → calculated access change. Do not estimate residents helped without an appropriate population model. A proposed curb ramp is not an implemented or approved repair.

## What the student can contribute

1. **Real local evidence.** Document 5–10 public locations with observation dates, photos where permitted, and specific conditions. Record mapped-versus-observed disagreement. Do not collect private home locations or identify people without permission.
2. **Rider feedback.** Invite a few actual transit riders with different mobility needs to try the same journey. Record consented, anonymized task results and changes made in response. Present the small sample honestly.
3. **Student technical work.** Choose a substantive component to implement, understand, and explain. Keep a contribution log and reproducible examples. Be able to explain graph construction, profile constraints, unknown evidence, algorithm tradeoffs, and the limits of the results.
4. **A focused 1–3 minute demo.** Show one actual public journey, its barrier evidence and detour, and a concrete useful output. Explain the original contribution and one hard technical problem. Avoid claiming unimplemented functionality or field verification.

## Performance and production prerequisites

The prepared stop/study snapshots already let the UI load without waiting for the routing engine. The county graph still needs initialization in a new Python server instance. Loading feedback improves visibility but does not eliminate this backend work. The map JavaScript bundle is also large and the base map depends on tile requests.

An always-running routing service or a more compact graph runtime is the next infrastructure improvement if consistent first-route latency is needed. A hosting budget/account decision would be needed before moving services. Public community submissions additionally need durable storage and a review/retraction workflow; the current Vercel deployment intentionally pauses reporting. No new paid infrastructure is required for the loader.
