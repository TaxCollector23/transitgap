"""Bounded adapter from real profile-cost graph evidence to inspection sensitivity."""
from collections import defaultdict
import networkx as nx
from .inspection_priority_student import rank_inspection_candidates

MAX_CANDIDATES = 12


def analyze_inspections(graph, *, stop_id, stop_node, origins, possible_dist, possible_paths,
                        seconds, profile, weight, unknowns, osm_values):
    network = nx.MultiDiGraph()
    network.add_nodes_from(set(origins) | set(possible_dist))
    groups = {}
    edge_groups = {}
    for u, v, key, attrs in graph.edges(keys=True, data=True):
        if u not in possible_dist or v not in possible_dist:
            continue
        cost = weight(graph, u, v, {key: attrs}, profile, 'possible')
        if cost is None:
            continue
        network.add_edge(u, v, key=key, walk_seconds=cost,
                         osmid=tuple(osm_values(attrs.get('osmid'))))
        missing = unknowns(attrs, graph.nodes[u], graph.nodes[v], profile)
        ways = sorted(osm_values(attrs.get('osmid')))
        if not ways:
            continue
        ends = sorted((str(u), str(v)))
        identity = f"osm-way:{','.join(ways)}:nodes:{':'.join(ends)}"
        item = groups.setdefault(identity, {'candidate_id': identity, 'source_url': f'https://www.openstreetmap.org/way/{ways[0]}',
                                            'edges': [], 'missing_critical_attributes': set()})
        item['edges'].append((u, v, key))
        item['missing_critical_attributes'].update(missing)
        if missing:
            edge_groups[(u, v, key)] = identity
    usage = defaultdict(set)
    for origin in origins:
        path = list(reversed(possible_paths.get(origin, [])))
        for u, v in zip(path, path[1:]):
            eligible = network.get_edge_data(u, v, default={})
            if not eligible:
                continue
            key = min(eligible, key=lambda k: (eligible[k]['walk_seconds'], str(k)))
            if identity := edge_groups.get((u, v, key)):
                usage[identity].add(origin)
    chosen = sorted(usage, key=lambda identity: (-len(usage[identity]), identity))[:MAX_CANDIDATES]
    results = rank_inspection_candidates(network, stop_nodes={str(stop_id): stop_node}, origin_nodes=origins,
                                        candidates=[groups[identity] for identity in chosen], time_budget_seconds=seconds)
    for result in results:
        result['missing_critical_attributes'] = sorted(groups[result['candidate_id']]['missing_critical_attributes'])
    return {
        'metric': 'sampled_journey_reachability_sensitivity',
        'method': 'Top 12 unknown physical segments by occurrence on deterministic shortest possible sample paths; then exact single-candidate blocked-versus-usable reachability within the time budget.',
        'candidate_limit': MAX_CANDIDATES, 'candidate_count_on_sample_paths': len(usage),
        'evaluated_candidate_count': len(results), 'sample_pair_count': len(set(origins)),
        'parallel_edge_policy': 'An OSM way plus unordered endpoint pair identifies one physical candidate; both mapped directions are blocked together. Distinct OSM ways remain alternatives.',
        'candidates': results,
    }
