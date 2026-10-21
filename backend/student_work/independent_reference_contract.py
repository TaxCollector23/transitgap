"""Run explicitly after the student implements independent_reference.py.
These tests deliberately FAIL until genuine student work is supplied.
"""
import networkx as nx
import pytest
from backend.student_work.independent_reference import reachable_origins


def test_direction_budget_and_isolation():
    g=nx.MultiDiGraph();g.add_weighted_edges_from([('a','b',1),('b','s',1),('s','x',1)],weight='length')
    assert reachable_origins(g,'s',2,lambda _:True)=={'a','b','s'}
    assert reachable_origins(g,'s',1,lambda _:True)=={'b','s'}


def test_parallel_connections_and_unknowns():
    g=nx.MultiDiGraph();g.add_edge(1,2,length=5,wheelchair='no');g.add_edge(1,2,length=20)
    allowed=lambda e:e.get('wheelchair')!='no'
    assert reachable_origins(g,2,10,allowed)=={2}
    assert reachable_origins(g,2,20,allowed)=={1,2}


def test_zero_length_cycle_terminates():
    g=nx.MultiDiGraph();g.add_edge(0,1,length=0);g.add_edge(1,0,length=0);g.add_edge(1,2,length=1)
    assert reachable_origins(g,2,1,lambda _:True)=={0,1,2}


def test_invalid_inputs_are_explicit():
    g=nx.MultiDiGraph();g.add_node('s')
    with pytest.raises(ValueError):reachable_origins(g,'s',-1,lambda _:True)
    for i in range(10):g.add_node(i)
    with pytest.raises(ValueError):reachable_origins(g,'s',1,lambda _:True)
