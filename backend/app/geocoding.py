"""Explicit address search, no autocomplete, bounded in-memory cache and 1 req/s."""

import time
from collections import OrderedDict
from threading import Lock
import httpx

_lock = Lock()
_last_request = 0.0
_cache = OrderedDict()


def search(query, boundary):
    global _last_request
    query = query.strip()
    if not 3 <= len(query) <= 200:
        raise ValueError("Enter between 3 and 200 characters.")
    now = time.monotonic()
    key = (query.casefold(), boundary.bounds)
    with _lock:
        cached = _cache.get(key)
        if cached and now - cached[0] < 600:
            return cached[1]
        if now - _last_request < 1.05:
            raise RuntimeError("Please wait a second before searching again.")
        _last_request = now
        west, south, east, north = boundary.bounds
        with httpx.Client(
            timeout=10,
            headers={
                "User-Agent": "TransitGap/1.0 (+https://github.com/TaxCollector23/transitgap)"
            },
        ) as client:
            response = client.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": query,
                    "format": "jsonv2",
                    "limit": 5,
                    "bounded": 1,
                    "viewbox": f"{west},{north},{east},{south}",
                    "countrycodes": "us",
                },
            )
            response.raise_for_status()
            from shapely.geometry import Point

            results = [
                {
                    "name": r["display_name"],
                    "latitude": float(r["lat"]),
                    "longitude": float(r["lon"]),
                }
                for r in response.json()
                if boundary.covers(Point(float(r["lon"]), float(r["lat"])))
            ]
        result = {
            "results": results,
            "attribution": "© OpenStreetMap contributors, Nominatim",
            "privacy": "Search text is sent to Nominatim. TransitGap keeps a bounded memory cache for 10 minutes; it does not persist addresses.",
        }
        _cache[key] = (now, result)
        while len(_cache) > 128:
            _cache.popitem(last=False)
        return result
