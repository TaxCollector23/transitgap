"""Source-linked candidates, never filled-in physical observations."""
import csv,gzip,json,re
from pathlib import Path
from shapely import from_wkt
root=Path(__file__).resolve().parents[1]
data=json.loads((root/'docs/benchmarks/performance-reachability.json').read_text())
candidates={}
for study in data['studies']:
    if study['policy']!='profile_required':continue
    for item in study['inspections']['candidates']:
        old=candidates.get(item['candidate_id'])
        if old is None or (item['score'] or 0)>(old['score'] or 0):
            candidates[item['candidate_id']]={**item,'stop_id':study['stop_id']}
ranked=sorted(candidates.values(),key=lambda x:(-(x['score'] or 0),x['candidate_id']))
crossings=[item for item in ranked if any('kerb' in k for k in item['missing_critical_attributes'])][:4]
chosen={item['candidate_id'] for item in crossings}
ordered=crossings+[item for item in ranked if item['candidate_id'] not in chosen][:8-len(crossings)]
by_pair={tuple(sorted(re.findall(r'nodes:(\d+):(\d+)',r['candidate_id'])[0])):r for r in ordered}
nodes={}
with gzip.open(root/'backend/data/walk-network-santa-clara-county.jsonl.gz','rt') as source:
    next(source)
    for line in source:
        kind,rows=json.loads(line)
        if kind=='nodes':
            for node,attrs in rows:nodes[str(node)]=(float(attrs['x']),float(attrs['y']))
        else:
            for u,v,key,attrs in rows:
                item=by_pair.get(tuple(sorted((str(u),str(v)))))
                if item is None or 'coordinates' in item:continue
                if attrs.get('geometry'):
                    point=from_wkt(attrs['geometry']).interpolate(.5,normalized=True)
                    item['coordinates']=(point.y,point.x)
                else:
                    a,b=nodes[str(u)],nodes[str(v)];item['coordinates']=((a[1]+b[1])/2,(a[0]+b[0])/2)
with (root/'docs/FIELD_CHECK_SHORTLIST.csv').open('w',newline='') as out:
    fields=['candidate_id','stop_id','latitude','longitude','osm_record','missing_attribute','expected_model_effect','actual_observation','observation_date','agreement_or_disagreement','notes']
    writer=csv.DictWriter(out,fieldnames=fields,lineterminator='\n');writer.writeheader()
    for item in ordered:
        lat,lon=item['coordinates']
        writer.writerow({'candidate_id':item['candidate_id'],'stop_id':item['stop_id'],'latitude':lat,'longitude':lon,'osm_record':item['source_url'],'missing_attribute':'; '.join(item['missing_critical_attributes']),'expected_model_effect':f"Hypothetically blocking this candidate changes {item['score']} of {item['sample_count']} sampled origin/stop pairs; all other unknowns remain usable"})
print('Wrote',len(ordered),'source-linked candidates. Physical observation fields remain blank.')
