"""Reproducible benchmark of the three real NetworkX routing algorithms."""
from __future__ import annotations

import argparse
import csv
import random
import statistics
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.data_loader import initialize  # noqa: E402
from app.models import Algorithm, Profile  # noqa: E402
from app.routing import _best_edge, _run  # noqa: E402

SEED = 7331
ALGORITHM_ORDER = (Algorithm.dijkstra, Algorithm.bidirectional_dijkstra, Algorithm.astar)


def percentile95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, int(0.95 * len(ordered) + 0.999999) - 1))]


def route_distance(graph, path: list[object]) -> float:
    return sum(_best_edge(graph, u, v, Profile.standard)[2] for u, v in zip(path, path[1:]))


def choose_pairs(stops: list[dict], count: int, seed: int) -> list[tuple[dict, dict]]:
    # Select distinct GTFS stops which each resolve to a real graph node. Do
    # not pre-filter by reachability: every attempted no-path is retained.
    unique = {}
    for stop in stops:
        node = stop["graph_node"]
        if isinstance(node, str) and node.isdigit():
            node = int(node)
        unique.setdefault(node, stop)
    values = list(unique.values())
    n = len(values)
    if n < 2:
        return []
    # Sample ordered pairs without allocating O(stops squared) combinations.
    indices = random.Random(seed).sample(range(n * (n - 1)), min(count, n * (n - 1)))
    result = []
    for index in indices:
        first, second = divmod(index, n - 1)
        if second >= first:
            second += 1
        result.append((values[first], values[second]))
    return result


def run_benchmark(pair_count: int = 30, repeats: int = 5, seed: int = SEED) -> tuple[Path, Path]:
    graph, stops = initialize()
    pairs = choose_pairs(stops, pair_count, seed)
    output_dir = Path(__file__).resolve().parent
    csv_path = output_dir / "results.csv"
    markdown_path = output_dir / "summary.md"
    if not pairs:
        raise RuntimeError("No distinct GTFS stop pairs resolve to walking graph nodes")

    rows: list[dict] = []
    timings: dict[str, list[float]] = {algorithm.value: [] for algorithm in ALGORITHM_ORDER}
    costs_by_pair: dict[int, dict[str, float]] = {i: {} for i in range(len(pairs))}
    successes = {algorithm.value: 0 for algorithm in ALGORITHM_ORDER}
    failures = {algorithm.value: 0 for algorithm in ALGORITHM_ORDER}

    for pair_index, (origin, destination) in enumerate(pairs, start=1):
        start_node = origin["graph_node"]
        end_node = destination["graph_node"]
        if isinstance(start_node, str) and start_node.isdigit():
            start_node = int(start_node)
        if isinstance(end_node, str) and end_node.isdigit():
            end_node = int(end_node)
        pair_costs = {}
        algorithm_order = random.Random(seed + pair_index).sample(ALGORITHM_ORDER, len(ALGORITHM_ORDER))
        for algorithm in algorithm_order:
            successful_repeat_costs = []
            for repeat in range(1, repeats + 1):
                started = perf_counter()
                try:
                    path, cost = _run(graph, start_node, end_node, algorithm, Profile.standard)
                    elapsed_ms = (perf_counter() - started) * 1000
                    physical_m = route_distance(graph, path)
                    success, error = True, ""
                    successes[algorithm.value] += 1
                    successful_repeat_costs.append(cost)
                except Exception as exc:  # Retain each failed query in CSV and summary.
                    elapsed_ms = (perf_counter() - started) * 1000
                    physical_m, cost = "", ""
                    success, error = False, f"{type(exc).__name__}: {exc}"
                    failures[algorithm.value] += 1
                timings[algorithm.value].append(elapsed_ms)
                rows.append({
                    "algorithm": algorithm.value,
                    "origin_stop_id": origin["stop_id"],
                    "origin_stop_name": origin["stop_name"],
                    "destination_stop_id": destination["stop_id"],
                    "destination_stop_name": destination["stop_name"],
                    "profile": Profile.standard.value,
                    "repeat": repeat,
                    "success": success,
                    "physical_distance_m": physical_m,
                    "optimal_weighted_cost": cost,
                    "execution_time_ms": round(elapsed_ms, 4),
                    "error": error,
                })
            if len(successful_repeat_costs) == repeats:
                pair_costs[algorithm.value] = statistics.median(successful_repeat_costs)
        costs_by_pair[pair_index - 1] = pair_costs

    fieldnames = list(rows[0])
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    comparable = [costs for costs in costs_by_pair.values() if len(costs) == len(ALGORITHM_ORDER)]
    agreements = sum(max(costs.values()) - min(costs.values()) <= 1e-6 for costs in comparable)
    summary = [
        "# TransitGap routing benchmark",
        "",
        f"- Fixed random seed: `{seed}`",
        f"- Requested pairs: {pair_count}; selected and attempted: {len(pairs)}",
        f"- Repeats per algorithm and pair: {repeats}",
        f"- Graph: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} directed edges",
        f"- Profile: `{Profile.standard.value}`; all algorithms use the same directed graph and edge costs",
        f"- Cost agreement: {agreements}/{len(comparable)} pairs where all algorithms found a route, tolerance 1e-6 m",
        "- Physical distance is the sum of selected OSM edge lengths; weighted cost is recorded separately.",
        "- Failed queries remain in the CSV and are counted below; they are not silently dropped.",
        "",
        "## Results",
        "",
        "| Algorithm | Successful runs | Failed runs | Median ms (all attempts) | P95 ms (all attempts) |",
        "|---|---:|---:|---:|---:|",
    ]
    for algorithm in ALGORITHM_ORDER:
        values = timings[algorithm.value]
        median = f"{statistics.median(values):.4f}" if values else "n/a"
        p95 = percentile95(values)
        p95_text = f"{p95:.4f}" if p95 is not None else "n/a"
        summary.append(f"| {algorithm.value} | {successes[algorithm.value]} | {failures[algorithm.value]} | {median} | {p95_text} |")
    summary.extend(["", "## Failed queries", ""])
    failed_rows = [row for row in rows if not row["success"]]
    if failed_rows:
        summary.extend(f"- {row['algorithm']} repeat {row['repeat']}: {row['origin_stop_name']} → {row['destination_stop_name']}: {row['error']}" for row in failed_rows)
    else:
        summary.append("No failed queries.")
    summary.extend([
        "",
        "## Interpretation limits",
        "",
        "These measurements cover this cached OSM graph and this machine only. They do not establish that one algorithm is universally faster. The benchmark records current timings; there is no pre-Phase-3 baseline in this file, so it makes no before/after performance claim.",
        "",
    ])
    markdown_path.write_text("\n".join(summary), encoding="utf-8")
    return csv_path, markdown_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=int, default=30)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    if args.pairs < 1 or args.repeats < 1:
        parser.error("--pairs and --repeats must be positive integers")
    csv_result, summary_result = run_benchmark(args.pairs, args.repeats, args.seed)
    print(f"Benchmark records: {csv_result}")
    print(f"Benchmark summary: {summary_result}")
