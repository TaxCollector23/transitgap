# Reproducible pilot evaluation

Run `backend/.venv/bin/python scripts/evaluate_pilot.py` against the prepared, cache-only county snapshot. Actual output, graph SHA-256, feed version, bounds, phase timings, memory and candidate results are in `docs/benchmarks/final-pilot.json`.

All rows use wheelchair rules, 10 minutes, and 150 deterministically selected graph origins in the fixed 1,500 m Diridon pilot. These nodes are not people or a population estimate.

| Actual VTA stop | Default documented / possible | Width-optional sensitivity documented / possible |
|---|---:|---:|
| 5459 | 0 / 7 | 1 / 7 |
| 4514 | 0 / 0 | 0 / 0 |
| 5460 | 0 / 9 | 0 / 9 |

The first default result is reproduced; missing width contributes to the restrictive documented network. The alternative removes only missing width as a required predicate; known width barriers, other relevant unknowns and all profile rules remain. It is a sensitivity experiment, not a validated replacement policy. Stop 4514 has no sampled reachable origins at this budget; that can arise from the bounded deterministic sample and does not imply nobody can reach it.

For 5459, the top evaluated source-linked connection is OSM way 674154528 between nodes 5681153689 and 6313417227. Blocking this one physical segment changes 7 of 150 sampled journeys in the possible model. The default reachable network contains 311 directed segments with width unknown, 27 with surface unknown, 157 with crossing kerb unknown and one with unparseable incline grade. These categories overlap and describe stored tags, not field findings.

Candidate selection is capped at 12 by occurrence on deterministic shortest possible sampled paths. Ranking then recomputes exact bounded reachability for each chosen candidate. Other unknowns stay usable in both scenarios. Equivalent records are grouped; distinct mapped ways remain alternatives. This is not a full ranking of all local infrastructure or a probability of accessibility.

Local correctness evidence: 131 backend/contract tests, independent exhaustive forward-path reference, 4 fixture browser tests and 11 real-data browser tests. No field truth set, consented rider session, physical accuracy percentage, adoption claim or completed CAC entry is available. See RELEASE_ACCEPTANCE.md for final hosted and CI outcomes.
