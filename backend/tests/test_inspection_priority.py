"""Independent correctness checks for AI-assisted hypothetical sensitivity."""
import math
import networkx as nx
import pytest
from backend.app.research.inspection_priority_student import rank_inspection_candidates as rank


def call(graph, candidates, origins=('o',), stops=None, budget=10):
    return rank(graph, origin_nodes=origins, stop_nodes=stops or {'vta': 's'},
                candidates=candidates, time_budget_seconds=budget)


def candidate(key=0, **extra):
    return {'candidate_id': 'c', 'edge': ('o', 's', key), 'source_url': 'https://www.openstreetmap.org/way/1', **extra}


@pytest.mark.parametrize('budget', [0, -1, math.inf, math.nan, 'invalid'])
def test_invalid_budget_rejected(budget):
    with pytest.raises(ValueError, match='budget'):
        call(nx.MultiDiGraph(), [], budget=budget)


@pytest.mark.parametrize('cost', [-1, math.inf, math.nan, None, 'unknown'])
def test_invalid_cost_rejected(cost):
    graph=nx.MultiDiGraph(); graph.add_edge('o','s',walk_seconds=cost)
    with pytest.raises(ValueError, match='walk_seconds'):
        call(graph, [candidate()])


def test_distinct_parallel_connection_retains_reach():
    graph=nx.MultiDiGraph()
    graph.add_edge('o','s',walk_seconds=2,osmid=1)
    graph.add_edge('o','s',walk_seconds=3,osmid=2)
    assert call(graph,[candidate()])[0]['score']==0


@pytest.mark.parametrize('alternate_cost,expected', [(3,0),(20,1)])
def test_alternate_route_budget_and_cycle(alternate_cost, expected):
    graph=nx.MultiDiGraph()
    graph.add_edge('o','s',walk_seconds=1)
    graph.add_edge('o','x',walk_seconds=alternate_cost)
    graph.add_edge('x','o',walk_seconds=1)
    graph.add_edge('x','s',walk_seconds=1)
    assert call(graph,[candidate()])[0]['score']==expected


def test_duplicates_and_explicit_physical_direction_group():
    graph=nx.MultiDiGraph();graph.add_edge('o','s',walk_seconds=1);graph.add_edge('s','o',walk_seconds=1)
    record=candidate(edges=[('o','s',0),('s','o',0)])
    result=call(graph,[record,dict(record)],origins=['o','o'])
    assert len(result)==1 and result[0]['score']==1 and result[0]['sample_count']==1


def test_missing_origin_or_cost_is_unavailable_or_invalid():
    graph=nx.MultiDiGraph();graph.add_edge('o','s',walk_seconds=1)
    assert call(graph,[candidate()],origins=['absent'])[0]['score'] is None
    del graph['o']['s'][0]['walk_seconds']
    with pytest.raises(ValueError):call(graph,[candidate()])


def test_same_candidate_id_cannot_refer_to_two_edges():
    graph=nx.MultiDiGraph();graph.add_edge('o','s',walk_seconds=1);graph.add_edge('o','x',walk_seconds=1)
    with pytest.raises(ValueError,match='conflicting'):
        call(graph,[candidate(),candidate(edge=('o','x',0))])


def test_independent_exhaustive_simple_path_reference():
    graph=nx.MultiDiGraph()
    for u,v,cost in [('a','u',1),('b','u',1),('u','s',2),('a','z',8),('z','s',8)]:
        graph.add_edge(u,v,walk_seconds=cost)
    original=graph.copy();blocked=graph.copy();blocked.remove_edge('u','s',0)
    def reachable(network, origin):
        return any(sum(network[u][v][k]['walk_seconds'] for u,v,k in path)<=10
                   for path in nx.all_simple_edge_paths(network,origin,'s'))
    expected={(o,'vta') for o in ['a','b'] if reachable(original,o)!=reachable(blocked,o)}
    result=call(graph,[candidate(edge=('u','s',0))],origins=['a','b'])[0]
    assert result['score']==len(expected)==2
    assert {tuple(pair) for pair in result['affected_pairs']}==expected
