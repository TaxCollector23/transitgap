import io
import json

import pytest

from scripts.monitor_backend import check


def test_monitor_actively_waits_for_readiness():
    now = [0]
    calls = []
    class Response(io.StringIO):
        status = 200
    def open_request(request, timeout):
        calls.append((request.full_url, request.method, timeout))
        return Response(json.dumps({'ready': len(calls) == 2}))
    check('https://example.test/', opener=open_request, clock=lambda: now[0],
          sleep=lambda seconds: now.__setitem__(0, now[0]+seconds))
    assert len(calls) == 2
    assert calls[0] == ('https://example.test/routing/initialize', 'POST', 25)


def test_monitor_times_out_instead_of_claiming_success():
    now = [0]
    def unavailable(*args, **kwargs):
        now[0] += kwargs['timeout']
        raise TimeoutError()
    with pytest.raises(TimeoutError, match='within 3 seconds'):
        check('https://example.test', budget=3, opener=unavailable,
              clock=lambda: now[0], sleep=lambda _: None)
    assert now[0] == 3


def test_monitor_does_not_retry_initialization_failure():
    class Response(io.StringIO):
        status = 200
    with pytest.raises(RuntimeError, match='initialization failure'):
        check('https://example.test', opener=lambda *a, **k:
              Response('{"ready":false,"error":"failed"}'))


def test_monitor_rejects_missing_configuration():
    with pytest.raises(ValueError, match='HTTPS'):
        check('')
