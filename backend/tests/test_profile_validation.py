import json
from datetime import datetime,timezone,timedelta
import networkx as nx
import pytest
from backend.app.models import Algorithm,Profile
from backend.app.profiles import assess,width_m
from backend.app.routing import _run,calculate_route

WEIGHTED=[a for a in Algorithm if a!=Algorithm.breadth_first]

def graph_with_shortcut(tags,node_tags=None):
    g=nx.MultiDiGraph()
    for i in range(4):g.add_node(i,x=-121.903+i*.00001,y=37.3296,**((node_tags or {}) if i==1 else {}))
    g.add_edge(0,1,key='shortcut',length=10,highway='footway',**tags)
    g.add_edge(1,3,length=10,highway='footway')
    g.add_edge(0,2,length=20,highway='footway',surface='asphalt',smoothness='good',width='2',incline='0')
    g.add_edge(2,3,length=20,highway='footway',surface='asphalt',smoothness='good',width='2',incline='0')
    return g

@pytest.mark.parametrize('tags',[{'highway':'steps'},{'wheelchair':'no'},{'smoothness':'impassable'},{'incline':'16%'},{'width':'.5'}])
def test_wheelchair_rejects_recorded_impassable_shortcuts(tags):
    tags=dict(tags);highway=tags.pop('highway',None)
    g=graph_with_shortcut(tags)
    if highway:g[0][1]['shortcut']['highway']=highway
    for algorithm in WEIGHTED:assert _run(g,0,3,algorithm,Profile.wheelchair)[0]==[0,2,3]

@pytest.mark.parametrize('profile',list(Profile))
def test_algorithms_agree_on_optimal_profile_cost(profile):
    g=graph_with_shortcut({'surface':'gravel','width':'0.65','incline':'9%'})
    results=[_run(g,0,3,a,profile) for a in WEIGHTED]
    assert [r[1] for r in results]==pytest.approx([results[0][1]]*len(results))

def test_stroller_width_and_wheelchair_permission_are_independent():
    edge={'width':'0.65','wheelchair':'no','surface':'asphalt'}
    assert not assess(edge,{},{},Profile.wheelchair).eligible
    assert assess(edge,{},{},Profile.stroller).eligible
    assert width_m('65 cm')==.65
    assert width_m('2 ft')==pytest.approx(.6096)

def test_unknown_crossings_are_not_certified_and_node_tags_apply():
    unknown=assess({'highway':'footway'},{'highway':'crossing'},{},Profile.low_vision)
    recorded=assess({'highway':'footway'},{'highway':'crossing','tactile_paving':'yes','traffic_signals:sound':'yes','crossing:signals':'yes'},{},Profile.low_vision)
    assert unknown.uncertainty_multiplier>recorded.uncertainty_multiplier
    assert 'kerb' in unknown.missing
    assert unknown.status=='unknown'
    assert not assess({'highway':'footway'},{'width':'0.4'},{},Profile.wheelchair).eligible

def test_low_vision_can_choose_longer_recorded_crossing():
    g=graph_with_shortcut({'crossing':'unmarked'})
    g.nodes[1]['highway']='crossing'
    g[0][2][0].update(highway='crossing',crossing='traffic_signals',tactile_paving='yes',**{'traffic_signals:sound':'yes','crossing:signals':'yes','lit':'yes'})
    g[2][3][0]['lit']='yes'
    assert _run(g,0,3,Algorithm.astar,Profile.standard)[0]==[0,1,3]
    assert _run(g,0,3,Algorithm.astar,Profile.low_vision)[0]==[0,2,3]

def test_parallel_identity_geometry_and_profile_cache_separation():
    g=graph_with_shortcut({})
    g.add_edge(0,1,key='narrow',length=2,width='0.3',highway='footway')
    stop={'stop_id':'fixture','stop_name':'Synthetic validation stop','latitude':g.nodes[3]['y'],'longitude':g.nodes[3]['x']}
    routes=[calculate_route(g,(37.3296,-121.903),3,a,Profile.wheelchair,stop) for a in WEIGHTED]
    assert all(r['selected_edges'][0]['key']=='shortcut' for r in routes)
    assert all(r['distance_m']==20 for r in routes)
    assert calculate_route(g,(37.3296,-121.903),3,Algorithm.astar,Profile.standard,stop)['distance_m']==12

def test_reviewed_effect_is_explicit_and_does_not_mutate_graph():
    g=graph_with_shortcut({})
    reference=json.dumps(['0','1','shortcut'],separators=(',',':'))
    effects={reference:{'routing_effect':'block','affected_profiles':['wheelchair']}}
    assert _run(g,0,3,Algorithm.astar,Profile.wheelchair,report_effects=effects)[0]==[0,2,3]
    assert _run(g,0,3,Algorithm.astar,Profile.standard,report_effects=effects)[0]==[0,1,3]
    assert _run(g,0,3,Algorithm.astar,Profile.wheelchair)[0]==[0,1,3]
    assert g.has_edge(0,1,'shortcut')

def test_disconnected_and_equal_cost_paths():
    g=graph_with_shortcut({});g[0][2][0]['length']=10;g[2][3][0]['length']=10
    assert all(_run(g,0,3,a,Profile.standard)[1]==20 for a in WEIGHTED)
    g.remove_edges_from(list(g.in_edges(3,keys=True)))
    with pytest.raises(nx.NetworkXNoPath):_run(g,0,3,Algorithm.astar,Profile.standard)
