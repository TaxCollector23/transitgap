"""Regional-cache experiment; never changes deployed coverage."""
import argparse,json,os,resource,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
parser=argparse.ArgumentParser();parser.add_argument('--region',choices=['diridon','santa_clara_county'],required=True);args=parser.parse_args()
os.environ['TRANSITGAP_CACHE_ONLY']='1';os.environ['TRANSITGAP_REGION']=args.region
start=time.perf_counter()
from backend.app.data_loader import initialize
g,stops=initialize()
print(json.dumps({'region':args.region,'import_graph_stops_seconds':round(time.perf_counter()-start,3),'nodes':len(g),'directed_edges':g.number_of_edges(),'stops':len(stops),'peak_rss_mib':round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if sys.platform=='darwin' else 1024),2),'deployment_change':False},indent=2))
