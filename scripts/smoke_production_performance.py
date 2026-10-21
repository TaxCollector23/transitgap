"""Read-only data plus real route POSTs; never creates community observations."""
import argparse,atexit,hashlib,json,time
from pathlib import Path
import httpx

parser=argparse.ArgumentParser();parser.add_argument('--url',default='https://transitgap.vercel.app');parser.add_argument('--output',default='docs/benchmarks/production-performance.json');parser.add_argument('--cold-first-route',action='store_true',help='Send one valid route as the first request to a newly deployed function, before warmup');args=parser.parse_args()
started=time.perf_counter();polls=[];report={'url':args.url,'status':'incomplete','definition':'Observed newly deployed worker; serverless instance placement and OS caches are not controlled','polls':polls}
def worker(response):
    return {key:response.headers.get(name) for key,name in {'instance_id':'x-transitgap-instance','request_id':'x-transitgap-request-id','request_number':'x-transitgap-request-number','initialization_phase':'x-transitgap-init-phase'}.items()}
atexit.register(lambda:Path(args.output).write_text(json.dumps(report,indent=2)+'\n'))
with httpx.Client(base_url=args.url,timeout=30) as client:
    if args.cold_first_route:
        tick=time.perf_counter()
        response=client.post('/route',json={'origin_latitude':37.32875,'origin_longitude':-121.90442,'destination_stop_id':'4514','algorithm':'astar','profile':'standard'},timeout=50)
        report['cold_first_route_request']={'seconds':round(time.perf_counter()-tick,3),'status':response.status_code,'worker':worker(response)}
        try:report['cold_first_route_request']['body']=response.json()
        except ValueError:report['cold_first_route_request']['body_type']='non_json'
        report['cold_first_route_request']['ready_before_request']=response.status_code==200
        Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
    deadline=time.monotonic()+140
    while time.monotonic()<deadline:
        tick=time.perf_counter()
        try:
            response=client.post('/routing/initialize',timeout=50)
            data=response.json();polls.append({'elapsed_seconds':round(time.perf_counter()-started,3),'request_seconds':round(time.perf_counter()-tick,3),'status':response.status_code,'worker':worker(response),'body':data})
            if 'first_route_request' not in report:
                tick=time.perf_counter()
                probe=client.post('/route',json={'origin_latitude':37.32875,'origin_longitude':-121.90442,'destination_stop_id':'4514','algorithm':'astar','profile':'standard'})
                report['first_route_request']={'seconds':round(time.perf_counter()-tick,3),'status':probe.status_code,'readiness_at_probe':data.get('ready'),'worker':worker(probe)}
            if data.get('ready'):break
            if data.get('error'):raise RuntimeError(data['error'])
        except httpx.HTTPError as error:polls.append({'elapsed_seconds':round(time.perf_counter()-started,3),'error':type(error).__name__})
        time.sleep(1)
    else:raise RuntimeError('Production routing did not become ready within 100 seconds')
    report['observed_ready_seconds']=round(time.perf_counter()-started,3)
    health=client.get('/health');health.raise_for_status();report['health']=health.json();report['health_worker']=worker(health)
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
    assert report['health']['ready'] and report['health']['reports_enabled']
    assert report['health']['community_report_storage']=='postgresql'
    bootstrap=client.get('/bootstrap.json');bootstrap.raise_for_status();stops=bootstrap.json()['stops']
    journeys=[('VTA',(37.32875,-121.90442),[s for s in stops if s['stop_id']=='4514']),('Caltrain',(37.3452,-121.977),[s for s in stops if s.get('agency')=='caltrain' and 'Santa Clara' in (s.get('station_name') or s['stop_name'])]),('BART',(37.364,-121.882),[s for s in stops if s.get('agency')=='bart' and 'Berryessa' in (s.get('station_name') or s['stop_name'])])]
    routes=[];report['routes']=routes
    for agency,point,candidates in journeys:
        stop=min(candidates,key=lambda s:(s['latitude']-point[0])**2+(s['longitude']-point[1])**2)
        for profile in ('standard','wheelchair','stroller','low_vision'):
            for repeat in range(2):
                tick=time.perf_counter()
                response=client.post('/route',json={'origin_latitude':point[0],'origin_longitude':point[1],'destination_stop_id':stop['stop_id'],'algorithm':'astar','profile':profile})
                response.raise_for_status();route=response.json()
                assert route['profile']==profile and route['geometry']['coordinates']
                routes.append({'agency':agency,'profile':profile,'repeat':repeat,'status':response.status_code,'seconds':round(time.perf_counter()-tick,3),'worker':worker(response),'distance_m':route['distance_m'],'directions':len(route.get('directions',[])),'arrival':route.get('arrival'),'geometry_sha256':hashlib.sha256(json.dumps(route['geometry'],sort_keys=True).encode()).hexdigest()})
    report['public_admin_status']=client.get('/admin/observations').status_code
    assert report['public_admin_status']==403
report['status']='passed'
Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'artifact':args.output,'reported_initialization_seconds':report['health']['initialization_seconds'],'observed_ready_seconds':report['observed_ready_seconds'],'routes_passed':len(report['routes']),'reports_enabled':report['health']['reports_enabled']},indent=2))
