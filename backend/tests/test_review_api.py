import json
from datetime import datetime,timedelta,timezone
from fastapi.testclient import TestClient
from backend.app import main
from backend.app.observations import initialize_observations
from test_profile_validation import graph_with_shortcut

def test_public_reports_cannot_review_and_authenticated_review_is_traceable(tmp_path,monkeypatch):
    monkeypatch.setenv('TRANSITGAP_OBSERVATIONS_DB',str(tmp_path/'reports.sqlite'))
    monkeypatch.delenv('DATABASE_URL',raising=False)
    monkeypatch.setenv('TRANSITGAP_MODERATION_TOKEN','test-reviewer-token-more-than-32-characters')
    initialize_observations()
    monkeypatch.setitem(main.state,'observations_ready',True)
    monkeypatch.setitem(main.state,'graph',graph_with_shortcut({}))
    main._report_rate.clear()
    client=TestClient(main.app)
    body={'latitude':37.3296,'longitude':-121.903,'category':'stairs','description':'Synthetic API validation only'}
    assert client.post('/accessibility/observations',json={**body,'review_status':'REVIEWED'}).status_code==422
    report=client.post('/accessibility/observations',json=body)
    assert report.status_code==201
    identity=report.json()['id']
    review={'status':'REVIEWED','reviewer':'test-reviewer','reason':'Synthetic documented review evidence','edge_reference':json.dumps(['0','1','shortcut'],separators=(',',':')),'routing_effect':'block','effective_until':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),'affected_profiles':['wheelchair']}
    path=f'/accessibility/observations/{identity}/review'
    assert client.post(path,json=review).status_code==403
    header={'Authorization':'Bearer test-reviewer-token-more-than-32-characters'}
    assert client.post(path,json={**review,'effective_until':None},headers=header).status_code==422
    response=client.post(path,json=review,headers=header)
    assert response.status_code==200,response.text
    assert response.json()['review_status']=='REVIEWED'
    assert len(client.get(f'/accessibility/observations/{identity}').json()['review_history'])==1
