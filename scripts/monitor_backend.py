"""Bounded active readiness probe; success does not prove route correctness."""
import json
import os
import time
import urllib.error
import urllib.request


def check(base, *, budget=90, opener=urllib.request.urlopen,
          clock=time.monotonic, sleep=time.sleep):
    base = base.rstrip('/')
    if not base.startswith('https://'):
        raise ValueError('TRANSITGAP_API_URL must be a public HTTPS origin')
    deadline = clock() + budget
    attempts = 0
    while clock() < deadline:
        attempts += 1
        try:
            request = urllib.request.Request(base + '/routing/initialize', method='POST')
            with opener(request, timeout=min(25, max(0.1, deadline-clock()))) as response:
                data = json.load(response)
                if response.status == 200 and data.get('ready'):
                    print(f'HTTP 200; ready=true after {attempts} readiness probes. No route calculated.')
                    return
                if data.get('error'):
                    raise RuntimeError('Backend reported an initialization failure')
        except urllib.error.HTTPError as error:
            if error.code < 500 and error.code != 429:
                raise RuntimeError(f'Readiness endpoint rejected probe: HTTP {error.code}') from error
        except (TimeoutError, urllib.error.URLError):
            pass
        remaining = deadline-clock()
        if remaining > 0:
            sleep(min(1, remaining))
    raise TimeoutError(f'Backend did not become ready within {budget} seconds')


if __name__ == '__main__':
    try:
        check(os.getenv('TRANSITGAP_API_URL', ''))
    except Exception as error:
        print('Backend health check failed:', str(error))
        raise SystemExit(1)
