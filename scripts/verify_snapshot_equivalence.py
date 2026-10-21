"""Compare every stored node/edge/attribute of two snapshots, excluding only
the recalculated A* numerical certificate. Runs sequentially to bound RAM.
"""
import argparse,gc,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.app.data_loader import read_compact_graph
parser=argparse.ArgumentParser()
parser.add_argument('snapshots',nargs=2)
parser.add_argument('--output',required=True)
args=parser.parse_args();results=[]
for path in args.snapshots:
    graph=read_compact_graph(Path(path));digest=hashlib.sha256()
    def record(row):digest.update(json.dumps(row,sort_keys=True,separators=(',',':')).encode()+b'\n')
    record({k:v for k,v in graph.graph.items() if k!='transitgap_heuristic_scale'})
    for row in graph.nodes(data=True):record(row)
    for row in graph.edges(keys=True,data=True):record(row)
    results.append({'file':Path(path).name,'nodes':len(graph),'directed_edges':graph.number_of_edges(),'all_attributes_sha256':digest.hexdigest()})
    del graph;gc.collect()
report={'equal':results[0]['all_attributes_sha256']==results[1]['all_attributes_sha256'],'snapshots':results}
Path(args.output).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if not report['equal']:raise SystemExit('Graph snapshots differ')
