import asyncio
import httpx
import pytest
from backend.app import main
from backend.app.models import RouteRequest


def test_warmup_holds_invocation_without_blocking_liveness(monkeypatch):
    async def scenario():
        monkeypatch.setitem(main.state,'graph',None)
        async def load():
            await asyncio.sleep(.03)
            main.state['graph']=object()
        future=asyncio.create_task(load())
        monkeypatch.setattr(main.app.state,'initialization',future,raising=False)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as client:
            warmup=asyncio.create_task(client.post('/routing/initialize'))
            await asyncio.sleep(.005)
            assert not (await client.get('/health/live')).json()['ready']
            assert not warmup.done()
            assert (await warmup).json()['ready']
    asyncio.run(scenario())


def test_warmup_timeout_does_not_cancel_initialization(monkeypatch):
    async def scenario():
        monkeypatch.setitem(main.state,'graph',None)
        async def load():
            await asyncio.sleep(.03)
            main.state['graph']=object()
        future=asyncio.create_task(load())
        monkeypatch.setattr(main.app.state,'initialization',future,raising=False)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as client:
            monkeypatch.setattr(main,'INITIALIZATION_REQUEST_SECONDS',.005)
            assert not (await client.post('/routing/initialize')).json()['ready']
            assert not future.cancelled()
            await future
            assert (await client.post('/routing/initialize')).json()['ready']
    asyncio.run(scenario())


def test_production_warmup_wait_exceeds_measured_cold_initialization():
    assert main.INITIALIZATION_REQUEST_SECONDS >= 35


def test_first_route_joins_shared_cold_initialization(monkeypatch):
    async def scenario():
        monkeypatch.setitem(main.state, 'graph', None)
        monkeypatch.setitem(main.state, 'groundtruth', None)

        async def load():
            await asyncio.sleep(.03)
            main.state['graph'] = object()

        future = asyncio.create_task(load())
        monkeypatch.setattr(main.app.state, 'initialization', future, raising=False)
        inputs = []

        def route_inputs(*args):
            inputs.append(main.state['graph'])
            return object(), {'stop_name': 'Test stop', 'graph_node': 'test-node'}

        monkeypatch.setattr(main, '_route_inputs', route_inputs)
        monkeypatch.setattr(main, 'calculate_route', lambda *args: {'geometry': {'coordinates': []}})
        payload = RouteRequest(origin_latitude=37.3, origin_longitude=-121.9,
                               destination_stop_id='test-stop')
        response = await main.route(payload)
        assert future.done() and not future.cancelled()
        assert response['groundtruth_evidence']['status'] == 'unavailable'
        assert len(inputs) == 1 and inputs[0] is not None

    asyncio.run(scenario())


def test_first_route_timeout_preserves_initialization_and_returns_bounded_503(monkeypatch):
    async def scenario():
        monkeypatch.setitem(main.state, 'graph', None)
        future = asyncio.create_task(asyncio.sleep(.03))
        monkeypatch.setattr(main.app.state, 'initialization', future, raising=False)
        monkeypatch.setattr(main, 'INITIALIZATION_REQUEST_SECONDS', .001)
        payload = RouteRequest(origin_latitude=37.3, origin_longitude=-121.9,
                               destination_stop_id='test-stop')
        with pytest.raises(main.HTTPException) as error:
            await main.route(payload)
        assert error.value.status_code == 503
        assert not future.cancelled()
        await future

    asyncio.run(scenario())
