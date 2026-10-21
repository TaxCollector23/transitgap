# Student explanation outline — complete in your own words

Do not submit this outline as a completed explanation. The student should document their actual choices and debugging work.

1. **Question:** What does “another inspection would help most” mean in this model?
2. **Inputs:** Which unknown candidates, directed graph, VTA stops, profiles, sample origins, and source IDs are considered?
3. **Scenarios:** How are candidate-passable and candidate-blocked cases simulated? What assumptions are held constant?
4. **Score:** Define the exact unique origin/stop/profile outcomes counted. Explain duplicate handling and null/incomplete evidence.
5. **Ordering:** Explain deterministic tie-breaking and what a score does not mean.
6. **Data structures and complexity:** State the graph/sample bounds and measured runtime after implementation.
7. **Correctness and tests:** Explain each contract fixture, especially direction, bridge, dead end, duplicates, ties, no candidates, and zero samples.
8. **Debugging story:** Describe one real bug the student found and fixed, with a reproducible test.
9. **Limitations:** Sampling bias, OSM provenance, unverified physical conditions, and no ridership/official-priority interpretation.

Student completion and review are pending.

## Current implementation (AI-assisted technical reference)

The possible graph has finite, nonnegative `walk_seconds` costs derived from the selected mobility profile. A reverse Dijkstra search at each stop finds baseline origin→stop outcomes within the time budget. For each candidate, a graph view hides its physical connection records, then searches again. The score is the cardinality of the symmetric difference of unique (origin, stop ID) outcomes. Missing node/edge data yields null impact; duplicate origins/records do not add fictitious journeys. Equal scores sort by candidate ID.

Identical parallel records are treated as duplicates. Distinct mapped ways remain alternatives. The application explicitly groups both directions of one OSM way/endpoint segment into one physical candidate. Other unknowns remain usable in both scenarios, so the output is a hypothetical single-candidate sensitivity, not a probability or field conclusion.

For k candidates and s stops, the core takes approximately O((k+1) s (E+V log V)) time plus pair-set bookkeeping. The application limits k to 12 and s to one; selects candidates by occurrence on deterministic sampled shortest possible paths; and reports how many candidates were omitted. This selection can miss candidates on tied alternatives. The independent reference test enumerates forward simple paths on a tiny graph instead of reusing Dijkstra.

This reference is AI-written; the student's explanation and personal contribution remain unfilled.
