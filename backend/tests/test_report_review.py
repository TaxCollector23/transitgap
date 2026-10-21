import json
from datetime import datetime,timedelta,timezone
from backend.app.observations import initialize_observations,create_observation,review_observation,active_routing_effects,observation_detail

def test_review_history_expiry_and_rejection(tmp_path):
    path=tmp_path/'reports.sqlite'
    initialize_observations(path)
    report=create_observation(latitude=37.33,longitude=-121.9,category='construction_obstruction',description='Synthetic test report',path=path)
    assert report['review_status']=='UNVERIFIED'
    assert active_routing_effects(path)=={}
    reference=json.dumps(['1','2','0'],separators=(',',':'))
    reviewed=review_observation(report['id'],status='REVIEWED',reviewer='test-reviewer',reason='Inspected synthetic test evidence',edge_reference=reference,routing_effect='block',effective_until=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),affected_profiles=['wheelchair'],path=path)
    assert len(reviewed['review_history'])==1
    assert active_routing_effects(path)[reference]['affected_profiles']==['wheelchair']
    initialize_observations(path)
    assert observation_detail(report['id'],path)['review_status']=='REVIEWED'
    review_observation(report['id'],status='OUTDATED',reviewer='test-reviewer',reason='Synthetic restriction expired',path=path)
    assert not active_routing_effects(path)
    assert len(observation_detail(report['id'],path)['review_history'])==2
