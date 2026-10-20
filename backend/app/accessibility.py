"""Evidence-aware summaries of accessibility tags found in OpenStreetMap."""
from __future__ import annotations

import os
from collections import defaultdict
from math import isfinite
from typing import Any

from .models import Profile

DEFAULT_UNCERTAINTY_PENALTIES = {
    "surface": 0.20,
    "smoothness": 0.15,
    "incline": 0.20,
    "wheelchair": 0.35,
    "crossing": 0.15,
    "kerb": 0.15,
    "tactile_paving": 0.10,
    "width": 0.10,
    "sidewalk": 0.10,
}

SUPPORTED_OSM_ATTRIBUTES = (
    "highway", "footway", "sidewalk", "crossing", "kerb", "surface",
    "smoothness", "incline", "wheelchair", "tactile_paving", "barrier",
    "width", "access", "foot",
)


def uncertainty_penalties() -> dict[str, float]:
    """Read deterministic nonnegative per-attribute weights from environment."""
    weights = {}
    for attribute, default in DEFAULT_UNCERTAINTY_PENALTIES.items():
        name = f"TRANSITGAP_UNCERTAINTY_PENALTY_{attribute.upper()}"
        try:
            value = float(os.getenv(name, str(default)))
        except ValueError as exc:
            raise ValueError(f"{name} must be a finite nonnegative number") from exc
        if not isfinite(value) or value < 0:
            raise ValueError(f"{name} must be a finite nonnegative number")
        weights[attribute] = value
    return weights


def _values(value: Any) -> list[str]:
    if value is None:
        return []
    parts = value if isinstance(value, (list, tuple, set)) else str(value).replace(";", ",").split(",")
    return [str(part).strip() for part in parts if str(part).strip()]


def _known(tags: dict[str, Any], key: str) -> bool:
    return bool(_values(tags.get(key)))


def is_mapped_stairs(tags: dict[str, Any]) -> bool:
    for key in ("highway", "footway", "indoor"):
        if any(value.lower() == "steps" for value in _values(tags.get(key))):
            return True
    return False


def _crossing_applies(edge: dict[str, Any], start: dict[str, Any], end: dict[str, Any]) -> bool:
    for tags in (edge, start, end):
        if any(value.lower() == "crossing" for value in _values(tags.get("highway"))):
            return True
        if _known(tags, "crossing"):
            return True
    return False


def _public_access(edge: dict[str, Any]) -> bool:
    """Honor explicit foot access, including its override of general access."""
    foot = [value.lower() for value in _values(edge.get("foot"))]
    access = [value.lower() for value in _values(edge.get("access"))]
    effective = foot if foot else access
    return not any(value in {"no", "private"} for value in effective)


def node_public_access(node: dict[str, Any]) -> bool:
    """A node restriction applies to traversal unless an explicit foot tag overrides it."""
    return _public_access(node)


def edge_uncertainty(edge: dict[str, Any], start: dict[str, Any], end: dict[str, Any],
                     profile: Profile, penalties: dict[str, float] | None = None) -> tuple[float, list[str], list[str]]:
    """Return the profile penalty and applicable known/missing tags for one edge."""
    weights = penalties if penalties is not None else uncertainty_penalties()
    crossing = _crossing_applies(edge, start, end)
    applicable = ["surface", "smoothness", "incline", "wheelchair", "width"]
    highway = " ".join(value.lower() for value in _values(edge.get("highway")))
    if highway in {"primary", "secondary", "tertiary", "residential", "unclassified", "service", "living_street"}:
        applicable.append("sidewalk")
    if crossing:
        applicable.extend(("crossing", "kerb", "tactile_paving"))
    missing = [attribute for attribute in applicable if not _known(edge, attribute)
               and not _known(start, attribute) and not _known(end, attribute)]
    known = [attribute for attribute in applicable if attribute not in missing]
    if profile == Profile.prefer_documented_paths:
        checked_weights = {attribute: float(weights.get(attribute, 0.0)) for attribute in applicable}
        if any(not isfinite(value) or value < 0 for value in checked_weights.values()):
            raise ValueError("Uncertainty penalties must be finite nonnegative numbers")
        penalty = sum(checked_weights[attribute] for attribute in missing)
    else:
        penalty = 0.0
    return penalty, known, missing


def analyze_route(segments: list[dict[str, Any]], connector_distance_m: float = 0.0) -> dict[str, Any]:
    """Summarize only tag observations that are present or logically applicable."""
    known_counts: dict[str, dict[str, Any]] = defaultdict(lambda: {"observations": 0, "distance_m": 0.0, "values": set()})
    missing_counts: dict[str, dict[str, Any]] = defaultdict(lambda: {"observations": 0, "distance_m": 0.0, "values": set()})
    surface_known = surface_missing = 0.0
    crossings: dict[str, bool] = {}
    stair_count = 0
    barrier_items: set[str] = set()
    explicit_access_segments = 0
    access_values: set[str] = set()
    details = []

    for index, segment in enumerate(segments, start=1):
        edge = segment["data"]
        start = segment["start"]
        end = segment["end"]
        length = float(segment["length_m"])
        crossing = _crossing_applies(edge, start, end)
        _, known, missing = edge_uncertainty(edge, start, end, Profile.standard, {})
        if is_mapped_stairs(edge):
            stair_count += 1
        for attribute in known:
            known_counts[attribute]["observations"] += 1
            known_counts[attribute]["distance_m"] += length
            for tags in (edge, start, end):
                known_counts[attribute]["values"].update(_values(tags.get(attribute)))
        for tags in (edge, start, end):
            access_values.update(f"{key}={value}" for key in ("access", "foot") for value in _values(tags.get(key)))
        if _known(edge, "access") or _known(edge, "foot") or _known(start, "access") or _known(start, "foot") or _known(end, "access") or _known(end, "foot"):
            explicit_access_segments += 1
        for attribute in missing:
            missing_counts[attribute]["observations"] += 1
            missing_counts[attribute]["distance_m"] += length
        if _known(edge, "surface"):
            surface_known += length
        else:
            surface_missing += length
        if crossing:
            edge_crossing = any(value.lower() == "crossing" for value in _values(edge.get("highway"))) or _known(edge, "crossing")
            crossing_nodes = [node_id for node_id, tags in ((segment.get("start_id"), start), (segment.get("end_id"), end))
                              if tags and (any(value.lower() == "crossing" for value in _values(tags.get("highway"))) or _known(tags, "crossing"))]
            crossing_ids = [f"edge:{segment.get('start_id')}:{segment.get('end_id')}:{segment.get('key')}" ] if edge_crossing else [f"node:{node_id}" for node_id in crossing_nodes]
            known_kerb = _known(edge, "kerb") or _known(start, "kerb") or _known(end, "kerb")
            for crossing_id in crossing_ids:
                crossings[crossing_id] = crossings.get(crossing_id, False) or known_kerb
        barrier_tags = []
        for source, tags in (("edge", edge), ("node", start), ("node", end)):
            if source == "edge":
                osm_id = f"{segment.get('start_id')}:{segment.get('end_id')}:{segment.get('key')}"
            elif tags is start:
                osm_id = segment.get("start_id")
            else:
                osm_id = segment.get("end_id")
            for value in _values(tags.get("barrier")):
                item = f"{source}:{osm_id}:{value}"
                barrier_items.add(item)
                barrier_tags.append(item)
        details.append({
            "segment": index,
            "distance_m": round(length, 1),
            "crossing_applies": crossing,
            "known_attributes": known,
            "missing_attributes": missing,
            "mapped_barriers": sorted(set(barrier_tags)),
            "documented_values": {attribute: sorted({value for tags in (edge, start, end)
                                                     for value in _values(tags.get(attribute))})
                                  for attribute in known},
            "source": "OpenStreetMap; not independently field verified",
        })

    def summaries(source: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        return [{"attribute": key, "observations": int(value["observations"]),
                 "distance_m": round(value["distance_m"], 1), "values": sorted(value.get("values", set()))}
                for key, value in sorted(source.items())]

    return {
        "source": "OpenStreetMap tags; not independently field verified",
        "mapped_stair_segments": stair_count,
        "known_mapped_barriers": sorted(barrier_items),
        "known_mapped_barrier_count": len(barrier_items),
        "pedestrian_access_information": {
            "explicitly_tagged_segments": explicit_access_segments,
            "segments_without_explicit_access_tags": len(segments) - explicit_access_segments,
            "segment_denominator": len(segments),
            "observed_tags": sorted(access_values),
        },
        "surface_distance_known_m": round(surface_known, 1),
        "surface_distance_missing_m": round(surface_missing, 1),
        "distance_denominator_m": round(sum(s["length_m"] for s in segments), 1),
        "crossing_observations": {
            "known_kerb_information": sum(crossings.values()),
            "unknown_kerb_information": len(crossings) - sum(crossings.values()),
            "denominator": len(crossings),
        },
        "documented_attributes": summaries(known_counts),
        "missing_attributes": summaries(missing_counts),
        "segment_observations": details,
        "connector_distance_m": round(connector_distance_m, 1),
        "interpretation": "More documented information does not guarantee greater accessibility. Missing information is unknown, not a barrier or proof of access.",
    }
