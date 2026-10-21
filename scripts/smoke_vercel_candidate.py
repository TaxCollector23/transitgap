"""Validate an unpromoted protected candidate through Vercel's authenticated CLI.
No bypass credential is extracted, logged or put in the repository.
"""
import argparse,json,re,subprocess,time
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--url',required=True);parser.add_argument('--output',default='docs/benchmarks/production-candidate.json');args=parser.parse_args()
report={'url':args.url,'status':'incomplete','warmup':[]}
output=Path(args.output)
def save():output.write_text(json.dumps(report,indent=2)+'\n')
def request(path,method='GET',body=None):
    command=['vercel','curl',path,'--deployment',args.url,'--','--request',method,'--max-time','55','--silent','--show-error','--include','--write-out','\nHTTP_STATUS:%{http_code}\n']
    if body is not None:command.extend(['--header','Content-Type: application/json','--data',json.dumps(body)])
    started=time.perf_counter();result=subprocess.run(command,capture_output=True,text=True,timeout=55)
    if result.returncode:raise RuntimeError(f'Candidate request failed: {path}, CLI exit {result.returncode}')
    payload,code=result.stdout.rsplit('HTTP_STATUS:',1)
    value=json.loads(payload[payload.index('{'):])
    headers={name.lower():value.strip() for name,value in re.findall(r'(?im)^((?:x-transitgap-[a-z-]+)):\s*(.*?)\s*$',payload)}
    return int(code.strip()),value,round(time.perf_counter()-started,3),headers
code,first_route,seconds,first_route_headers=request('/route','POST',{'origin_latitude':37.32875,'origin_longitude':-121.90442,'destination_stop_id':'4514','algorithm':'astar','profile':'standard'})
report['first_route_before_warmup']={'status':code,'cli_request_seconds':seconds,'profile':first_route.get('profile'),'distance_m':first_route.get('distance_m'),'headers':first_route_headers};save()
for _ in range(4):
    code,data,seconds,headers=request('/routing/initialize','POST')
    report['warmup'].append({'status':code,'body':data,'worker':headers,'cli_request_seconds':seconds});save()
    if data.get('ready'):break
    if data.get('error'):raise RuntimeError('Candidate initialization failed')
else:raise RuntimeError('Candidate did not become ready after four bounded warmup requests')
report['health_attempts']=[]
for _ in range(4):
    code,health,seconds,headers=request('/health')
    report['health_attempts'].append({'status':code,'ready':health.get('ready'),'request_seconds':seconds,'worker':headers})
    report['health']=health;report['health_worker']=headers;save()
    if code==200 and health.get('ready'):break
    code,data,seconds,headers=request('/routing/initialize','POST')
    report['warmup'].append({'status':code,'body':data,'worker':headers,'cli_request_seconds':seconds});save()
else:raise RuntimeError('No sampled worker was ready after health verification')
assert code==200 and health['ready'] and health['reports_enabled'] and health['community_report_storage']=='postgresql'
code,route,seconds,headers=request('/route','POST',{'origin_latitude':37.32875,'origin_longitude':-121.90442,'destination_stop_id':'4514','algorithm':'astar','profile':'wheelchair'})
assert code==200 and route.get('geometry') and route.get('profile')=='wheelchair'
report['real_route']={'status':code,'distance_m':route['distance_m'],'profile':route['profile'],'worker':headers,'cli_request_seconds':seconds}
code,bootstrap,_,headers=request('/bootstrap.json')
assert code==200 and bootstrap.get('stops')
report['bootstrap_worker']=headers
journeys=[('VTA',(37.32875,-121.90442),[s for s in bootstrap['stops'] if s['stop_id']=='4514']),('Caltrain',(37.3452,-121.977),[s for s in bootstrap['stops'] if s.get('agency')=='caltrain' and 'Santa Clara' in (s.get('station_name') or s['stop_name'])]),('BART',(37.364,-121.882),[s for s in bootstrap['stops'] if s.get('agency')=='bart' and 'Berryessa' in (s.get('station_name') or s['stop_name'])])]
report['routes']=[]
for agency,point,candidates in journeys:
    stop=min(candidates,key=lambda s:(s['latitude']-point[0])**2+(s['longitude']-point[1])**2)
    for profile in ('standard','wheelchair','stroller','low_vision'):
        try:
            code,journey,seconds,headers=request('/route','POST',{'origin_latitude':point[0],'origin_longitude':point[1],'destination_stop_id':stop['stop_id'],'algorithm':'astar','profile':profile})
            ok=code==200 and journey.get('profile')==profile and bool(journey.get('geometry',{}).get('coordinates'))
            report['routes'].append({'agency':agency,'profile':profile,'status':code,'ok':ok,'seconds':seconds,'worker':headers,'distance_m':journey.get('distance_m')})
        except Exception as error:
            report['routes'].append({'agency':agency,'profile':profile,'status':None,'ok':False,'error':type(error).__name__})
        save()
report['route_success_count']=sum(route['ok'] for route in report['routes'])
report['route_count']=len(report['routes'])
report['status']='passed' if report['route_success_count']==report['route_count']==12 else 'partial'
save()
print(json.dumps({'artifact':str(output),'cold_first_route_status':report['first_route_before_warmup']['status'],'initialization_seconds':health['initialization_seconds'],'cpu_seconds':health.get('initialization_cpu_seconds'),'schedule_cache_hits':health.get('schedule_cache_hits'),'memory':health.get('process_memory'),'agency_profile_successes':report['route_success_count'],'agency_profile_routes':report['route_count'],'status':report['status']},indent=2))
if report['status']!='passed':raise SystemExit('One or more production agency/profile journeys failed; see the saved artifact.')
