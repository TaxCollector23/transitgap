"""Plain-data snapshot of expensive evidence analysis, prepared at build time."""

from __future__ import annotations
import gzip
import hashlib
import json
from pathlib import Path
from shapely import from_wkb
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree
from .groundtruth import GroundTruthIndex


def load_groundtruth(graph, stops, city, directory, graph_signature):
    source = Path(__file__).parent
    code_digest = hashlib.sha256(
        b"".join(
            (source / name).read_bytes()
            for name in (
                "groundtruth.py",
                "groundtruth_cache.py",
                "routing.py",
                "profiles.py",
            )
        )
    ).hexdigest()
    signature = [
        graph_signature,
        code_digest,
        hashlib.sha256(
            json.dumps(city.get("features", []), sort_keys=True).encode()
        ).hexdigest(),
    ]
    path = directory / "evidence-index-v1.json.gz"

    def decode(value):
        if set(value) == {"__geometry_wkb__"}:
            return from_wkb(bytes.fromhex(value["__geometry_wkb__"]))
        return value

    if path.exists():
        try:
            with gzip.open(path, "rt") as source_file:
                payload = json.load(source_file, object_hook=decode)
            if payload["signature"] == signature:
                index = GroundTruthIndex.__new__(GroundTruthIndex)
                index.__dict__.update(payload["index"])
                city_records = {r["id"]: r for r in index.city_records}
                osm_records = {r["id"]: r for r in index.osm_records}
                for item in index.gaps:
                    item["city_record"] = city_records.get(item.pop("city_record_id"))
                    item["osm_record"] = osm_records.get(item.pop("osm_record_id"))
                index.by_id = {item["id"]: item for item in index.gaps}
                index.city_tree = (
                    STRtree([r["geometry_m"] for r in index.city_records])
                    if index.city_records
                    else None
                )
                index.osm_tree = (
                    STRtree([r["geometry_m"] for r in index.osm_records])
                    if index.osm_records
                    else None
                )
                return index
        except (OSError, ValueError, KeyError, TypeError):
            pass
    index = GroundTruthIndex(graph, stops, city)
    packed = {
        key: value
        for key, value in index.__dict__.items()
        if key not in {"city_tree", "osm_tree", "by_id", "gaps"}
    }
    packed["gaps"] = [
        {
            **{k: v for k, v in item.items() if k not in {"city_record", "osm_record"}},
            "city_record_id": (item.get("city_record") or {}).get("id"),
            "osm_record_id": (item.get("osm_record") or {}).get("id"),
        }
        for item in index.gaps
    ]

    def encode(value):
        if isinstance(value, BaseGeometry):
            return {"__geometry_wkb__": value.wkb_hex}
        if hasattr(value, "item"):
            return value.item()
        raise TypeError(f"Unsupported evidence cache value: {type(value).__name__}")

    try:
        temporary = path.with_suffix(".part")
        with gzip.open(temporary, "wt") as output:
            json.dump(
                {"signature": signature, "index": packed},
                output,
                default=encode,
                separators=(",", ":"),
            )
        temporary.replace(path)
    except OSError:
        pass  # Runtime caches can be read-only; the in-memory index still works.
    return index
