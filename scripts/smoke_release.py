"""Read-only external release smoke; routes are queries, no reports are created."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time
import urllib.request

parser=argparse.ArgumentParser()
parser.add_argument('--url',default='https://transitgap.vercel.app')
parser.add_argument('--expected-sha')
parser.add_argument('--output',default='docs/benchmarks/production-smoke.json')
args=parser.parse_args()
base=args.url.rstrip('/')
checks=[]

def request(path, body=None):
    start=time.perf_counter()
    payload=json.dumps(body).encode() if body is not None else None
    req=urllib.request.Request(base+path,data=payload,headers={'Content-Type':'application/json'} if payload else {})
    with urllib.request.urlopen(req,timeout=90) as response:
        raw=response.read()
        item={'path':path,'http_status':response.status,'seconds':round(time.perf_counter()-start,3),'bytes':len(raw)}
        checks.append(item)
        print(json.dumps(item),flush=True)
        return (json.loads(raw) if 'application/json' in response.headers.get('content-type','') else raw.decode()),item

root,_=request('/')
assert 'id="root"' in root
app,_=request('/app')
assert 'id="root"' in app
asset=re.search(r'src="(/assets/[^\"]+\.js)"',root).group(1)
request(asset)
health,item=request('/health')
assert health['ready'] is True
if args.expected_sha:assert health['build_sha']==args.expected_sha
item.update(build_sha=health['build_sha'],initialization_seconds=health['initialization_seconds'],reports_enabled=health['reports_enabled'],storage=health['community_report_storage'])
stops,item=request('/stops');item['count']=stops['count'];assert stops['count']>0
coverage,item=request('/coverage');item['region']=coverage['region']
pilot,item=request('/accessibility/reachability/stops');item['count']=pilot['stop_count'];assert pilot['stop_count']>0
study,item=request('/accessibility/reachability/5459?profile=wheelchair&minutes=10&sample_size=150')
item.update(study_status=study['status'],documented=study['documented']['reachable_sample_origins'],possible=study['possible']['reachable_sample_origins'],sample_count=study['sampling']['origin_sample_count'],inspections=study['inspection_priorities']['evaluated_candidate_count'],top_candidate=study['inspection_priorities']['candidates'][:1])
assert item['documented']<=item['possible']
assert study['inspection_priorities']['metric']=='sampled_journey_reachability_sensitivity'
for candidate in study['inspection_priorities']['candidates']:
    assert candidate['score']==len({tuple(pair) for pair in candidate['affected_pairs']})
route,item=request('/route',{'origin_latitude':37.32875,'origin_longitude':-121.90442,'destination_stop_id':'4514','profile':'wheelchair','algorithm':'astar'})
item.update(distance_m=route['distance_m'],segment_count=len(route['segments']),profile=route['profile'])
assert route['segments'] and route['geometry']['type']=='LineString'
priorities,item=request('/accessibility/priorities?limit=1');item['metric']=priorities['metric'];assert priorities['metric']=='route_proximity_weighted_review_score'
request('/data-sources')
report={'url':base,'verified_at':datetime.now(timezone.utc).isoformat(),'result':'PASS','checks':checks}
output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n')
print('PASS: external release smoke',flush=True)
