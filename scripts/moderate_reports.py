"""Authenticated reviewer CLI. Token stays in the environment, never the URL."""
import argparse
import json
import os
import httpx

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--url',default='https://transitgap.vercel.app')
parser.add_argument('--id',help='Omit to list the review queue')
parser.add_argument('--status',choices=['UNDER_REVIEW','REVIEWED','REJECTED','OUTDATED'])
parser.add_argument('--reviewer',default='reviewer')
parser.add_argument('--reason')
parser.add_argument('--edge',help='JSON [u,v,key], only for supported mapped associations')
parser.add_argument('--effect',default='none',choices=['none','block','rough_surface'])
parser.add_argument('--until',help='ISO UTC date with timezone; required for an effect')
parser.add_argument('--profiles',nargs='*',default=['wheelchair','stroller'])
args=parser.parse_args()
token=os.environ.get('TRANSITGAP_MODERATION_TOKEN','')
if len(token)<32:parser.error('Set TRANSITGAP_MODERATION_TOKEN in your private environment')
with httpx.Client(base_url=args.url.rstrip('/'),headers={'Authorization':'Bearer '+token},timeout=30) as client:
    if args.id:
        if not args.status or not args.reason:parser.error('--status and --reason are required for review')
        response=client.post('/accessibility/observations/'+args.id+'/review',json={'status':args.status,'reviewer':args.reviewer,'reason':args.reason,'edge_reference':args.edge,'routing_effect':args.effect,'effective_until':args.until,'affected_profiles':args.profiles})
    else:
        response=client.get('/admin/observations')
    response.raise_for_status()
    print(json.dumps(response.json(),indent=2))
