"""Fresh-process benchmark: python scripts/benchmark_startup.py --output report.json.

OS filesystem caches are not flushed. 'cold' means a fresh Python process;
'warm' means repeated initialization inside that process. No network downloads.
"""
import argparse
import hashlib
import json
import os
import platform
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
parser = argparse.ArgumentParser()
parser.add_argument('--output', required=True)
args = parser.parse_args()
os.environ['TRANSITGAP_CACHE_ONLY'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ.pop('DATABASE_URL', None)
os.environ['TRANSITGAP_OBSERVATIONS_DB'] = str(Path(tempfile.mkdtemp()) / 'reports.sqlite3')
began = time.perf_counter()
from backend.app import main, data_loader
from backend.app.models import Algorithm, Profile
import_seconds = time.perf_counter() - began
stages = {}
def instrument(module, name):
    original = getattr(module, name)
    def measured(*a, **kw):
        start = time.perf_counter()
        try:
            return original(*a, **kw)
        finally:
            stages[name] = stages.get(name, 0) + time.perf_counter() - start
    setattr(module, name, measured)
for module, names in ((data_loader, ['load_graph', 'load_stops']), (main, ['load_agency_stops', 'TransitSchedule', 'nearest_graph_node', 'GapIndex', 'load_sidewalks', 'load_groundtruth', 'initialize_observations'])):
    for name in names:
        instrument(module, name)
started = time.perf_counter()
main._load()
cold = time.perf_counter() - started
if main.state['error']:
    raise RuntimeError(main.state['error'])
cold_stages = dict(stages)
graph = main.state['graph']
routes = {}
for agency, point in [('VTA', (37.32875, -121.90442)), ('Caltrain', (37.3452, -121.977)), ('BART', (37.364, -121.882))]:
    candidates = [s for s in main.state['transit_stops'] if s.get('agency', 'VTA').lower() == agency.lower()]
    stop = min(candidates, key=lambda s: (s['latitude']-point[0])**2 + (s['longitude']-point[1])**2)
    for profile in (Profile.standard, Profile.wheelchair, Profile.stroller, Profile.low_vision):
        samples = []
        for _ in range(3):
            start = time.perf_counter()
            route = main.calculate_route(graph, point, stop['graph_node'], Algorithm.astar, profile, stop)
            samples.append(round((time.perf_counter()-start)*1000, 3))
        stable = {k: route.get(k) for k in ('distance_m', 'duration_seconds', 'optimization_cost_m', 'selected_edges', 'geometry', 'arrival', 'directions', 'accessibility_summary')}
        routes[f'{agency}/{profile.value}'] = {'stop_id':stop['stop_id'], 'milliseconds': samples, 'distance_m':route['distance_m'], 'output_sha256':hashlib.sha256(json.dumps(stable,sort_keys=True).encode()).hexdigest()}
start = time.perf_counter()
study = main._reachability_study()
reachability_seconds = time.perf_counter()-start
start = time.perf_counter()
main._load()
warm = time.perf_counter()-start
peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2 if sys.platform=='darwin' else 1024)
rss = int(subprocess.check_output(['ps','-o','rss=','-p',str(os.getpid())]).strip())/1024
report = {'python':platform.python_version(),'platform':platform.platform(),'definition':'fresh interpreter, OS filesystem caches not flushed; warm repeats initialization in process', 'import_seconds':round(import_seconds,3),'cold_initialization_seconds':round(cold,3),'warm_initialization_seconds':round(warm,3),'cold_stages_seconds':{k:round(v,3) for k,v in cold_stages.items()},'steady_rss_mib':round(rss,2),'peak_rss_mib':round(peak,2),'nodes':len(graph),'directed_edges':graph.number_of_edges(),'agency_counts':{agency:sum(s.get('agency','VTA').lower()==agency.lower() for s in main.state['transit_stops']) for agency in ('VTA','Caltrain','BART')},'reachability_index_seconds':round(reachability_seconds,3),'routes':routes}
Path(args.output).parent.mkdir(parents=True,exist_ok=True)
Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2),flush=True)
