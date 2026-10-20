"""Student-owned information-value ranking contract.

The student must implement this core. See docs/STUDENT_ALGORITHM_EXPLANATION.md
and backend/student_work/test_inspection_priority_contract.py. Do not replace
this stub with an agent-authored implementation and attribute it to the student.
"""
from __future__ import annotations

from typing import Any, Sequence

import networkx as nx


def rank_inspection_candidates(
    graph: nx.MultiDiGraph,
    *,
    stop_nodes: dict[str, Any],
    origin_nodes: Sequence[Any],
    candidates: Sequence[dict[str, Any]],
    time_budget_seconds: float,
) -> list[dict[str, Any]]:
    """Return deterministic inspection-value results; student implements core.

    Contract: compare unique (origin_node, stop_id) reachability outcomes when
    a candidate edge is included versus blocked, traveling toward each stop.
    Preserve candidate IDs/source URLs and disclose sample count/assumptions.
    """
    raise NotImplementedError("Student: implement and explain the inspection-value algorithm")
