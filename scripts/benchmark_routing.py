"""Reproducible real-cache benchmark. Never downloads datasets when cache-only is set."""
import json
import os
import platform
import resource
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.data_loader import initialize, data_dir
from backend.app.models import Algorithm, Profile
from backend.app.routing import calculate_route

started = time.perf_counter()
graph, stops = initialize()
load_seconds = time.perf_counter() - started
stop = next(s for s in stops if s['stop_id'] == '4514')
measurements = {}
for profile in (Profile.standard, Profile.wheelchair, Profile.stroller, Profile.low_vision):
    runs = [calculate_route(graph, (37.32875, -121.90442), stop['graph_node'], Algorithm.astar, profile, stop) for _ in range(5)]
    measurements[profile.value] = {'distance_m': runs[-1]['distance_m'], 'optimization_cost_m': runs[-1]['optimization_cost_m'], 'median_request_ms': round(statistics.median(r['computation_time_ms'] for r in runs), 3), 'selected_edges': runs[-1].get('selected_edges')}
peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
report = {'python': platform.python_version(), 'region':os.getenv('TRANSITGAP_REGION','auto'), 'nodes':len(graph), 'edges':graph.number_of_edges(), 'graph_and_stops_load_seconds':round(load_seconds,3), 'rss_mib':round(int(subprocess.check_output(['ps','-o','rss=','-p',str(os.getpid())]).strip())/1024,2), 'peak_rss_mib':round(peak/(1024**2 if sys.platform=='darwin' else 1024),2), 'cache_size_mib':round(sum(p.stat().st_size for p in data_dir().glob('*') if p.is_file())/1024**2,2), 'routes': measurements}
print(json.dumps(report,indent=2))
