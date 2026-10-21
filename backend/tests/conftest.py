"""Use real cached data only when an integration test is actually selected."""
import networkx as nx
import pytest
from fastapi.testclient import TestClient
from backend.app import main


@pytest.fixture(scope='session',autouse=True)
def isolate_inherited_report_storage(tmp_path_factory):
    """Never inherit a production URL into any test or session startup."""
    with pytest.MonkeyPatch.context() as patch:
        patch.delenv('DATABASE_URL',raising=False)
        patch.delenv('TRANSITGAP_REPORTS_MIGRATED',raising=False)
        patch.setenv('TRANSITGAP_OBSERVATIONS_DB',str(tmp_path_factory.mktemp('session-reports')/'reports.sqlite3'))
        yield


@pytest.fixture(scope='session')
def client(request, tmp_path_factory):
    # The MCP SDK session manager has one lifecycle per ASGI application.
    real_data_selected = any(item.get_closest_marker('integration') for item in request.session.items)
    with pytest.MonkeyPatch.context() as patch:
        if not real_data_selected:
            directory=tmp_path_factory.mktemp('api-fixture')
            graph=nx.MultiDiGraph(crs='epsg:4326')
            graph.add_node('o',x=-121.903,y=37.3296)
            graph.add_node('s',x=-121.902,y=37.3296)
            graph.add_edge('o','s',length=100,highway='footway',osmid=42)
            stops=[{'stop_id':'synthetic-unit','stop_name':'Synthetic unit test stop',
                    'latitude':37.3296,'longitude':-121.902,'graph_node':'s'}]
            patch.setattr(main,'initialize',lambda:(graph,stops))
            patch.setattr(main,'data_dir',lambda:directory)
            patch.setattr(main,'TransitSchedule',lambda *a,**kw:None)
            patch.setattr(main,'load_sidewalks',lambda **kw:{'type':'FeatureCollection','features':[],
                                                          'metadata':{'availability':'unit fixture'}})
            patch.setenv('TRANSITGAP_OBSERVATIONS_DB',str(directory/'reports.sqlite3'))
            patch.delenv('DATABASE_URL',raising=False)
        with TestClient(main.app,base_url='http://localhost') as test_client:
            yield test_client
