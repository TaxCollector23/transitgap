"""Cache-only reproducible pilot sensitivity and startup/route measurement.

Run after scripts/prepare_deployment_data.py. Writes actual JSON, never field data.
"""
import argparse
from collections import defaultdict
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['TRANSITGAP_CACHE_ONLY']='1'
from backend.app import main
from backend.app.data_loader import data_dir, graph_cache_path
from backend.app.models import Algorithm, Profile
from backend.app.routing import calculate_route

parser=argparse.ArgumentParser()
parser.add_argument('--output', default='docs/benchmarks/final-pilot.json')
args=parser.parse_args()
timings=defaultdict(list)
for name in ['initialize','nearest_graph_node','GapIndex','TransitSchedule','load_sidewalks','load_groundtruth','initialize_observations']:
    original=getattr(main,name)
    def measured(*a,_name=name,_original=original,**kw):
        start=time.perf_counter()
        try:return _original(*a,**kw)
        finally:timings[_name].append(round(time.perf_counter()-start,4))
    setattr(main,name,measured)
main._load()
if main.state['error']:raise RuntimeError(main.state['error'])
first_startup=main.state['initialization_seconds']
main._load()
warm_startup=main.state['initialization_seconds']
index=main._reachability_study()
path=graph_cache_path(data_dir(),main.state['radius_m'],main.state['region'])
digest=sha256()
with path.open('rb') as source:
    for block in iter(lambda:source.read(1024*1024),b''):digest.update(block)
results=[]
for stop_id in ['5459','4514','4513']:
    if stop_id not in index.stops:
        continue
    for policy in ['profile_required','width_optional_sensitivity']:
        start=time.perf_counter()
        result=index.analyze(stop_id,Profile.wheelchair,10,150,policy)
        results.append({
            'stop_id':stop_id,'policy':policy,'status':result['status'],'seconds':round(time.perf_counter()-start,4),
            'sample_count':result.get('sampling',{}).get('origin_sample_count'),
            'documented':result.get('documented',{}).get('reachable_sample_origins'),
            'possible':result.get('possible',{}).get('reachable_sample_origins'),
            'missing_attributes':result.get('unknown_gap',{}).get('missing_attribute_edge_counts'),
            'inspections':result.get('inspection_priorities'),
        })
stop=next(s for s in main.state['stops'] if s['stop_id']=='4514')
routes=[]
for profile in [Profile.standard,Profile.wheelchair,Profile.stroller,Profile.low_vision]:
    row={'profile':profile.value,'runs':[]}
    for _ in range(2):
        start=time.perf_counter()
        route=calculate_route(main.state['graph'],(37.32875,-121.90442),stop['graph_node'],Algorithm.astar,profile,stop)
        row['runs'].append({'wall_seconds':round(time.perf_counter()-start,4),'distance_m':route['distance_m']})
    routes.append(row)
report={'dataset_sha256':digest.hexdigest(),'graph_file':path.name,'graph_nodes':len(index.graph),
        'directed_edges':index.graph.number_of_edges(),'pilot_radius_m':1500,'pilot_stop_count':len(index.stops),
        'gtfs':index.feed_info,'source_metadata':index.metadata,'sampling':'SHA256 ordering v1, 150 nodes per stop, excluding stop node',
        'first_prepared_process_startup_seconds':first_startup,'second_in_process_startup_seconds':warm_startup,
        'phase_seconds':dict(timings),'peak_rss_mib':round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if sys.platform=='darwin' else 1024),2),
        'routes':routes,'studies':results}
output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'artifact':str(output),'startup_first':first_startup,'startup_second':warm_startup,'studies':[{k:r[k] for k in ['stop_id','policy','status','documented','possible','seconds']} for r in results]},indent=2))
