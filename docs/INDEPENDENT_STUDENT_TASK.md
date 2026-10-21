# Independent student contribution

The existing production inspection code is AI-assisted. Its historical filename
does not establish student authorship. The new `independent_reference.py` contains
only a specification and `NotImplementedError`; the student must write its core.

## Task

Build an independent exhaustive reference for directed reachability on at most
nine nodes. Return every origin that can reach a given stop over eligible keyed
edges with total `length` at most `budget_m`. Include the stop itself. Handle
parallel edges individually and terminate on zero-length cycles. Reject negative
budgets, graphs exceeding nine nodes, missing stops and nonfinite/negative edge
lengths with `ValueError`. The `allowed(attributes)` predicate is supplied by the
caller; absent tags are not automatically affirmative accessibility evidence.

Use enumeration of simple paths or another independently explained exhaustive
method. Do not call NetworkX shortest-path or reachability algorithms. Study
`backend/app/reachability.py`, `backend/app/routing.py`, and the production
inspection adapter, then write your own solution without copying their core.

## Acceptance and benchmark

Run `backend/.venv/bin/python -m pytest backend/student_work/independent_reference_contract.py -q`.
The four supplied tests fail until the student implements the function. Add
independently designed tests for a disconnected origin, invalid lengths and a
budget exactly equal to the path length. Compare sets against reverse Dijkstra
on seeded graphs of 3–9 nodes, all four mobility predicates, both documentation
scenarios and multiple budgets. Report mismatches, runtime and graph seed;
do not replace a disagreement with a rounded score. Removing a candidate edge
must not increase reachable origins under nonnegative weights. Count distinct
origin/stop pairs once when comparing candidate effects.

Record your commit, design notes and measured results. Explain directionality,
parallel edges, why simple paths suffice for nonnegative weights, the exponential
worst case of exhaustive enumeration versus Dijkstra, the difference between
missing evidence and a known obstacle, and why sampled origins are not people.
This independent reference can validate the production model without making
experimental student code part of live routing.

No independent student implementation, field visit, human usability session or
submission receipt has been supplied in this sprint.
