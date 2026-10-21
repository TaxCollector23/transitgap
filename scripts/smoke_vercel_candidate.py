"""Validate an unpromoted protected candidate through Vercel's authenticated CLI.
No bypass credential is extracted, logged or put in the repository.
"""
import argparse,json,subprocess,time
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--url',required=True);args=parser.parse_args()
report={'url':args.url,'status':'incomplete','warmup':[]}
output=Path('docs/benchmarks/production-candidate.json')
def save():output.write_text(json.dumps(report,indent=2)+'\n')
def request(path,method='GET',body=None):
    command=['vercel','curl',path,'--deployment',args.url,'--','--request',method,'--max-time','40','--silent','--show-error','--write-out','\nHTTP_STATUS:%{http_code}\n']
    if body is not None:command.extend(['--header','Content-Type: application/json','--data',json.dumps(body)])
    started=time.perf_counter();result=subprocess.run(command,capture_output=True,text=True,timeout=55)
    if result.returncode:raise RuntimeError(f'Candidate request failed: {path}, CLI exit {result.returncode}')
    payload,code=result.stdout.rsplit('HTTP_STATUS:',1)
    value=json.loads(payload[payload.index('{'):])
    return int(code.strip()),value,round(time.perf_counter()-started,3)
for _ in range(6):
    code,data,seconds=request('/routing/initialize','POST')
    report['warmup'].append({'status':code,'body':data,'cli_request_seconds':seconds});save()
    if data.get('ready'):break
    if data.get('error'):raise RuntimeError('Candidate initialization failed')
else:raise RuntimeError('Candidate never became ready')
code,health,_=request('/health');report['health']=health;save()
assert code==200 and health['ready'] and health['reports_enabled'] and health['community_report_storage']=='postgresql'
code,route,seconds=request('/route','POST',{'origin_latitude':37.32875,'origin_longitude':-121.90442,'destination_stop_id':'4514','algorithm':'astar','profile':'wheelchair'})
assert code==200 and route.get('geometry') and route.get('profile')=='wheelchair'
report['real_route']={'status':code,'distance_m':route['distance_m'],'profile':route['profile'],'cli_request_seconds':seconds}
report['status']='passed';save()
print(json.dumps({'artifact':str(output),'initialization_seconds':health['initialization_seconds'],'cpu_seconds':health.get('initialization_cpu_seconds'),'schedule_cache_hits':health.get('schedule_cache_hits'),'memory':health.get('process_memory'),'route_status':code},indent=2))
