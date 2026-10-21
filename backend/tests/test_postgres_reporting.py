"""Opt-in, isolated PostgreSQL integration; never uses production DATABASE_URL."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from backend.app import main, observations
from backend.app.models import Algorithm, Profile
from test_profile_validation import graph_with_shortcut


@pytest.fixture
def pg(monkeypatch):
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo, conninfo_to_dict
    url=os.getenv('TRANSITGAP_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Set TRANSITGAP_TEST_DATABASE_URL to an isolated *_test database')
    assert conninfo_to_dict(url)['dbname'].endswith('_test'), 'Refusing a non-test database'
    schema='report_test_'+uuid.uuid4().hex
    with psycopg.connect(url) as c:
        c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    monkeypatch.setenv('DATABASE_URL',make_conninfo(url,options='-csearch_path='+schema))
    monkeypatch.delenv('TRANSITGAP_REPORTS_MIGRATED',raising=False)
    monkeypatch.setenv('TRANSITGAP_REPORT_RATE_SECRET','isolated-test-rate-secret-00000000000')
    monkeypatch.setenv('TRANSITGAP_MODERATION_TOKEN','isolated-test-review-secret-00000000')
    observations.initialize_observations()
    monkeypatch.setitem(main.state,'observations_ready',True)
    monkeypatch.setitem(main.state,'graph',graph_with_shortcut({}))
    monkeypatch.setitem(main.state,'region','diridon')
    monkeypatch.setitem(main.state,'radius_m',1500)
    monkeypatch.setitem(main.state,'groundtruth',None)
    main._report_rate.clear()
    yield TestClient(main.app)
    with psycopg.connect(url) as c:
        c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


BODY={'latitude':37.3296,'longitude':-121.903,'category':'stairs','description':'SYNTHETIC ISOLATED DATABASE TEST'}


def test_pg_saved_reload_idempotency_validation_and_history(pg):
    key=str(uuid.uuid4());headers={'Idempotency-Key':key}
    first=pg.post('/accessibility/observations',json=BODY,headers=headers)
    assert first.status_code==201,first.text
    report=first.json();identity=report['id']
    assert 'submission_key' not in report and report['review_status']=='UNVERIFIED'
    assert pg.post('/accessibility/observations',json=BODY,headers=headers).json()['id']==identity
    assert pg.post('/accessibility/observations',json={**BODY,'description':'Different'},headers=headers).status_code==409
    assert pg.post('/accessibility/observations',json={**BODY,'website':'spam.test'}).status_code==422
    assert pg.post('/accessibility/observations',json={**BODY,'category':'invalid'}).status_code==422
    assert TestClient(main.app).get('/accessibility/observations/'+identity).json()['id']==identity
    assert observations.active_routing_effects()=={}
    path='/accessibility/observations/'+identity+'/review'
    review={'status':'REVIEWED','reviewer':'isolated-test','reason':'Synthetic test evidence only','edge_reference':json.dumps(['0','1','shortcut'],separators=(',',':')),'routing_effect':'block','effective_until':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),'affected_profiles':['wheelchair']}
    assert pg.get('/admin/observations').status_code==403
    assert pg.post(path,json=review).status_code==403
    auth={'Authorization':'Bearer isolated-test-review-secret-00000000'}
    assert pg.post(path,json=review,headers=auth).status_code==200
    effects=observations.active_routing_effects()
    from backend.app.routing import _run
    graph=main.state['graph']
    assert _run(graph,0,3,Algorithm.astar,Profile.wheelchair,report_effects=effects)[0]==[0,2,3]
    assert _run(graph,0,3,Algorithm.astar,Profile.standard,report_effects=effects)[0]==[0,1,3]
    revoked={**review,'status':'OUTDATED','routing_effect':'none','effective_until':None}
    assert pg.post(path,json=revoked,headers=auth).status_code==200
    assert observations.active_routing_effects()=={}
    assert len(observations.observation_detail(identity)['review_history'])==2
    assert pg.get('/admin/observations',headers=auth).json()['count']==1


def test_pg_quota_is_atomic_across_connections(pg):
    with ThreadPoolExecutor(max_workers=10) as pool:
        allowed=list(pool.map(lambda _:observations.consume_report_quota('synthetic-shared-hash'),range(10)))
    assert sum(allowed)==5
    future=datetime.now(timezone.utc)+timedelta(minutes=2)
    assert observations.consume_report_quota('synthetic-shared-hash',now=future)


def test_pg_unavailable_store_never_confirms_save(pg,monkeypatch):
    monkeypatch.setattr(main,'consume_report_quota',lambda _:(_ for _ in ()).throw(ConnectionError('synthetic outage')))
    response=pg.post('/accessibility/observations',json=BODY)
    assert response.status_code==503 and 'not been saved' in response.json()['detail']
    monkeypatch.setattr(main,'observation_detail',lambda _:(_ for _ in ()).throw(ConnectionError('synthetic outage')))
    review={'status':'REVIEWED','reviewer':'isolated-test','reason':'Synthetic documented evidence','edge_reference':'["0","1","shortcut"]','routing_effect':'block','effective_until':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),'affected_profiles':['wheelchair']}
    response=pg.post('/accessibility/observations/missing/review',json=review,headers={'Authorization':'Bearer isolated-test-review-secret-00000000'})
    assert response.status_code==503
    monkeypatch.setitem(main.state,'observations_ready',False)
    with monkeypatch.context() as patch:
        patch.setattr(main,'active_routing_effects',lambda:(_ for _ in ()).throw(ConnectionError('synthetic outage')))
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as failure:main._routing_effects()
        assert failure.value.status_code==503
    assert main._routing_effects()=={}
    assert main.state['observations_ready']
