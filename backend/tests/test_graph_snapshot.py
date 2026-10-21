import gzip
import json
import networkx as nx
import pytest
from backend.app.data_loader import read_compact_graph, write_compact_graph, _write_legacy_graph
from backend.app.routing import _run
from backend.app.models import Algorithm, Profile


def test_snapshot_preserves_all_attributes_parallel_edges_reverse_views_and_costs(tmp_path):
    graph=nx.MultiDiGraph(crs='epsg:4326',source='synthetic regression')
    graph.add_node(1,x=-121.9,y=37.3,kerb='lowered',nested={'a':[1,2]})
    graph.add_node(2,x=-121.899,y=37.3)
    graph.add_edge(1,2,key=7,length=100,highway='footway',surface='asphalt',names=['a','b'])
    graph.add_edge(1,2,key='stairs',length=10,highway='steps',incline='30%')
    graph.add_edge(2,1,key=8,length=101,highway='footway',geometry='LINESTRING (-121.899 37.3, -121.9 37.3)')
    for writer in (write_compact_graph,_write_legacy_graph):
        path=tmp_path/(writer.__name__+'.gz');writer(graph,path)
        restored=read_compact_graph(path)
        assert dict(restored.nodes(data=True))==dict(graph.nodes(data=True))
        assert list(restored.edges(keys=True,data=True))==list(graph.edges(keys=True,data=True))
        assert restored._succ[1][2] is restored._pred[2][1]
        assert set(restored.reverse(copy=False).edges(keys=True))=={(2,1,7),(2,1,'stairs'),(1,2,8)}
        for algorithm in Algorithm:
            for profile in Profile:
                assert _run(restored,1,2,algorithm,profile)==_run(graph,1,2,algorithm,profile)
        restored.add_edge(1,2,key='extra',length=200)
        assert restored.number_of_edges()==4
        restored.remove_edge(1,2,'extra')
        assert restored.number_of_edges()==3


def test_invalid_snapshot_does_not_certify_unsafe_astar_bound(tmp_path):
    graph=nx.MultiDiGraph()
    graph.add_node('a',x=0,y=0);graph.add_node('b',x=.1,y=0)
    graph.add_edge('a','b',length=float('inf'))
    path=tmp_path/'invalid.gz';write_compact_graph(graph,path)
    assert read_compact_graph(path).graph['transitgap_heuristic_scale']==0


def test_duplicate_edge_keys_are_rejected(tmp_path):
    path=tmp_path/'invalid.gz'
    with gzip.open(path,'wt') as out:
        for row in ({'format':'transitgap-graph/2','attributes':{}},['nodes',[[1,{'x':0,'y':0}],[2,{'x':1,'y':0}]]],['edges',[[1,2,0,{'length':1}],[1,2,0,{'length':2}]]]):
            out.write(json.dumps(row)+'\n')
    with pytest.raises(ValueError,match='Duplicate'):
        read_compact_graph(path)
