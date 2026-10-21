import asyncio
import httpx
from backend.app import main


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
        monkeypatch.setattr(main,'INITIALIZATION_REQUEST_SECONDS',.005)
        async def load():
            await asyncio.sleep(.03)
            main.state['graph']=object()
        future=asyncio.create_task(load())
        monkeypatch.setattr(main.app.state,'initialization',future,raising=False)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://test') as client:
            assert not (await client.post('/routing/initialize')).json()['ready']
            assert not future.cancelled()
            await future
            assert (await client.post('/routing/initialize')).json()['ready']
    asyncio.run(scenario())
