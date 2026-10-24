"""Build-time snapshots for read-only evidence endpoints.

These responses are derived from the same graph and evidence index used by the
API, but can be served before a serverless worker has loaded the full graph.
"""

from __future__ import annotations

import gzip
import json
from functools import lru_cache
from pathlib import Path
from typing import Any


DATA_SOURCES_FILE = "public-data-sources-v1.json"
PRIORITIES_FILE = "public-accessibility-priorities-v1.json.gz"
REACHABILITY_STOPS_FILE = "public-reachability-stops-v1.json"


def with_agency_sources(result: dict[str, Any], transit_sources: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Append official transit feed metadata using the public API schema."""
    response = {**result, "sources": list(result.get("sources", []))}
    for agency_id, source in transit_sources.items():
        response["sources"].append({
            "id": f"{agency_id}-gtfs",
            "name": f"{source['name']} GTFS scheduled stops",
            "status": "ready",
            "url": source["developer_url"],
            "feed_url": source["feed_url"],
            "feature_count": source["stop_count"],
            "feed_info": source["feed_info"],
            "evidence_status": "SOURCE_DOCUMENTED",
            "limitations": "Agency-published scheduled transit data and stop coordinates; this does not describe sidewalk access or real-time service.",
        })
    return response


def _json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Unsupported public snapshot value: {type(value).__name__}")


def write_public_api_snapshots(
    directory: Path,
    index: Any,
    transit_sources: dict[str, dict[str, Any]],
    reachability_stops: dict[str, Any] | None = None,
) -> None:
    """Persist public evidence responses that are safe before graph startup."""
    directory.mkdir(parents=True, exist_ok=True)
    sources = with_agency_sources(index.source_status(), transit_sources)
    priorities = index.get_priorities(limit=max(1, len(index.gaps)), offset=0)

    sources_path = directory / DATA_SOURCES_FILE
    sources_temp = sources_path.with_suffix(sources_path.suffix + ".part")
    sources_temp.write_text(
        json.dumps(sources, default=_json_default, separators=(",", ":")),
        encoding="utf-8",
    )
    sources_temp.replace(sources_path)

    priorities_path = directory / PRIORITIES_FILE
    priorities_temp = priorities_path.with_suffix(priorities_path.suffix + ".part")
    with gzip.open(priorities_temp, "wt", encoding="utf-8", compresslevel=6) as output:
        json.dump(priorities, output, default=_json_default, separators=(",", ":"))
    priorities_temp.replace(priorities_path)

    if reachability_stops is not None:
        stops_path = directory / REACHABILITY_STOPS_FILE
        stops_temp = stops_path.with_suffix(stops_path.suffix + ".part")
        stops_temp.write_text(
            json.dumps(reachability_stops, default=_json_default, separators=(",", ":")),
            encoding="utf-8",
        )
        stops_temp.replace(stops_path)


@lru_cache(maxsize=8)
def _read_snapshot(path: str, modified_ns: int, compressed: bool) -> dict[str, Any]:
    del modified_ns  # Included in the cache key so rebuilt files invalidate it.
    opener = gzip.open if compressed else open
    with opener(path, "rt", encoding="utf-8") as source:
        value = json.load(source)
    if not isinstance(value, dict):
        raise ValueError("Public API snapshot must contain a JSON object")
    return value


def read_public_api_snapshot(directory: Path, filename: str, *, compressed: bool = False) -> dict[str, Any] | None:
    path = directory / filename
    try:
        stat = path.stat()
        return _read_snapshot(str(path.resolve()), stat.st_mtime_ns, compressed)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def page_priorities(snapshot: dict[str, Any], limit: int, offset: int) -> dict[str, Any]:
    """Apply API pagination to the immutable full candidate list."""
    return {
        **snapshot,
        "limit": limit,
        "offset": offset,
        "candidates": snapshot.get("candidates", [])[offset : offset + limit],
    }
