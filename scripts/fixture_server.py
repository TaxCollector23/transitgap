"""Local-only deterministic CI server. Never run this module in production."""
import os,tempfile
from pathlib import Path
import networkx as nx
os.environ['TRANSITGAP_OBSERVATIONS_DB']=str(Path(tempfile.mkdtemp(prefix='transitgap-ci-'))/'observations.sqlite3')
os.environ['CORS_ORIGINS']='http://127.0.0.1:5174'
os.environ['TRANSITGAP_MODERATION_TOKEN']='ci-only-synthetic-review-token-0000000000'
from backend.app import main

def fixture():
    graph=nx.MultiDiGraph(crs='epsg:4326',source='SYNTHETIC CI FIXTURE; not actual geographic observations')
    for n,(x,y) in enumerate([(-121.90442,37.32875),(-121.90430,37.32875),(-121.90430,37.32890),(-121.90442,37.32890)]):graph.add_node(n,x=x,y=y)
    for u,v,length,tags in [(0,1,20,{'highway':'steps'}),(0,3,25,{'highway':'footway','surface':'asphalt','width':'1.5','incline':'0','smoothness':'good'}),(3,1,25,{'highway':'footway','surface':'asphalt'}),(1,2,20,{'highway':'footway'})]:
        graph.add_edge(u,v,length=length,**tags);graph.add_edge(v,u,length=length,**tags)
    return graph,[{'stop_id':'ci-stop','stop_name':'SYNTHETIC CI Stop','latitude':37.32875,'longitude':-121.90430,'graph_node':1,'wheelchair_boarding':0}]
main.initialize=fixture
main.TransitSchedule=lambda *args,**kwargs:None
main.load_sidewalks=lambda **kwargs:{'type':'FeatureCollection','features':[],'metadata':{'availability':'synthetic CI fixture'}}
main.data_dir=lambda:Path(tempfile.gettempdir())/'transitgap-ci-cache'
main.data_dir().mkdir(exist_ok=True)
app=main.app
