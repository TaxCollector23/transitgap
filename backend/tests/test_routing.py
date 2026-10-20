import networkx as nx
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import shape
from app.main import app
from app.models import Algorithm, Profile
from app.routing import calculate_route, _run

def graph():
    g=nx.MultiDiGraph()
    # A 10 m square-ish network; straight-line distances stay below edge weights for A*.
    coords={0:(37.32960,-121.90300),1:(37.32969,-121.90300),2:(37.32978,-121.90300),3:(37.32960,-121.90282)}
    for n,(lat,lon) in coords.items(): g.add_node(n,y=lat,x=lon)
    def edge(a,b,length,highway='footway'):
        g.add_edge(a,b,length=length,highway=highway)
    edge(0,1,10);edge(1,2,10);edge(0,2,25);edge(0,3,15);edge(3,2,15)
    return g

def test_dijkstra_finds_minimum_cost_path():
    path,cost=_run(graph(),0,2,Algorithm.dijkstra,Profile.standard)
    assert path==[0,1,2] and cost==20

def test_bidirectional_dijkstra_matches_minimum_cost():
    path,cost=_run(graph(),0,2,Algorithm.bidirectional_dijkstra,Profile.standard)
    assert cost==20 and path[0]==0 and path[-1]==2

def test_astar_matches_minimum_cost():
    path,cost=_run(graph(),0,2,Algorithm.astar,Profile.standard)
    assert cost==20 and path[0]==0 and path[-1]==2

def test_avoid_mapped_stairs_excludes_stair_edges():
    g=nx.MultiDiGraph()
    for n,lat in [(0,37.32960),(1,37.32969),(2,37.32978)]:g.add_node(n,y=lat,x=-121.903)
    g.add_edge(0,2,length=4,highway='steps')
    g.add_edge(0,1,length=8,highway='footway');g.add_edge(1,2,length=8,highway='footway')
    path,cost=_run(g,0,2,Algorithm.dijkstra,Profile.avoid_mapped_stairs)
    assert path==[0,1,2] and cost==16

def test_disconnected_graph_returns_clear_route_error():
    g=nx.MultiDiGraph()
    g.add_node(0,y=37.3296,x=-121.903);g.add_node(1,y=37.3300,x=-121.903)
    stop={"stop_id":"vta-1","stop_name":"Test Stop","latitude":37.3300,"longitude":-121.903}
    with pytest.raises(LookupError,match="No walking route connects"):
        calculate_route(g,(37.3296,-121.903),1,Algorithm.dijkstra,Profile.standard,stop)

def test_invalid_api_inputs_are_rejected():
    client=TestClient(app)
    response=client.post('/route',json={"origin_latitude":120,"origin_longitude":-121.9,"destination_stop_id":"vta-1"})
    assert response.status_code==422
    missing=client.post('/route',json={"origin_latitude":37.3,"origin_longitude":-121.9})
    assert missing.status_code==422

def test_route_geometry_is_valid_geojson():
    g=graph();stop={"stop_id":"vta-1","stop_name":"Test Stop","latitude":37.32978,"longitude":-121.903}
    result=calculate_route(g,(37.32960,-121.903),2,Algorithm.dijkstra,Profile.standard,stop)
    geometry=shape(result['geometry'])
    assert result['geometry']['type']=='LineString' and geometry.is_valid and geometry.length>0
    assert result['distance_m']>0 and result['algorithm']=='dijkstra'
