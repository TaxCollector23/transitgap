"""Transparent routing assumptions, not an accessibility certification.

8% is a conservative concern threshold, close to the ADA 1:12 ramp maximum
(8.33%): https://www.access-board.gov/ada/guides/chapter-4-ramps-and-curb-ramps/
It is a model preference, not a test of legal compliance. Unknown slopes stay
unknown. Ordinal incline up/down indicates direction, not a measured grade.
All multipliers are >= 1 so geographic A* remains admissible. Positive tags
remove an uncertainty penalty rather than creating sub-distance costs.
"""

from __future__ import annotations
import re
from .accessibility import _values, _crossing_applies, is_mapped_stairs

SLOPE_CONCERN_PERCENT = 8.0
ROUGH_SURFACES = {"gravel", "unpaved", "dirt", "grass", "sett", "cobblestone", "sand"}
ROUGH_SMOOTHNESS = {"bad", "very_bad", "horrible", "very_horrible", "impassable"}
IMPASSABLE_BARRIERS = {"kissing_gate", "stile", "turnstile"}
SPEED_MPS = {
    "standard": 1.2,
    "wheelchair": 0.9,
    "avoid_mapped_stairs": 0.9,
    "stroller": 0.9,
    "low_vision": 1.2,
    "prefer_documented_paths": 1.2,
}
OBJECTIVES = {
    "standard": "Minimize mapped walking distance",
    "wheelchair": "Exclude mapped steps, wheelchair prohibitions, raised crossing kerbs and restrictive barriers; prefer documented surfaces and crossings",
    "avoid_mapped_stairs": "Wheelchair profile (legacy alias)",
    "stroller": "Exclude mapped steps and restrictive barriers; prefer firm surfaces and easier slopes",
    "low_vision": "Prefer documented tactile paving, audible or signal-controlled crossings and lighting",
    "prefer_documented_paths": "Minimize distance weighted by missing applicable map attributes",
}


def values(tags, key):
    return {v.lower() for v in _values(tags.get(key))}


def incline_percent(value):
    """Parse a numeric percent; directional and ambiguous grades remain unknown."""
    if value is None or isinstance(value, (list, tuple)):
        return None
    match = re.fullmatch(r"\s*([+-]?\d+(?:\.\d+)?)\s*%?\s*", str(value))
    return abs(float(match[1])) if match else None


def evaluate(edge, start, end, profile):
    """Return eligibility, cost multiplier and provenance for one selected edge.

    Surface/width/incline describe the edge only. A single endpoint surface tag
    must not be extrapolated over the entire segment. Crossing tags apply only
    at a mapped crossing. No OSM record is independently field checked here.
    """
    name = getattr(profile, "value", profile)
    if name == "avoid_mapped_stairs":
        name = "wheelchair"
    crossing = _crossing_applies(edge, start, end)
    places = (edge, start, end)
    restrictions = []
    if is_mapped_stairs(edge):
        restrictions.append("Mapped stairs")
    if any("no" in values(t, "wheelchair") for t in places):
        restrictions.append("Mapped wheelchair=no")
    if any(values(t, "barrier") & IMPASSABLE_BARRIERS for t in places):
        restrictions.append("Mapped restrictive barrier")
    if crossing and any("raised" in values(t, "kerb") for t in places):
        restrictions.append("Mapped raised kerb at crossing")
    if name in {"wheelchair", "stroller"} and restrictions:
        return False, 1.0, "concern", restrictions, []

    known, missing, concerns = [], [], list(restrictions)
    required = ["surface", "smoothness", "incline", "width"]
    for key in required:
        (known if values(edge, key) else missing).append(key)
    if crossing:
        for key in ("kerb", "crossing", "tactile_paving"):
            (known if any(values(t, key) for t in places) else missing).append(key)
    factor = 1.0
    if values(edge, "surface") & ROUGH_SURFACES:
        concerns.append("Mapped loose or uneven surface")
        if name in {"wheelchair", "stroller"}:
            factor += 1.5 if name == "wheelchair" else 1.0
    if values(edge, "smoothness") & ROUGH_SMOOTHNESS:
        concerns.append("Mapped poor smoothness")
        if name in {"wheelchair", "stroller"}:
            factor += 1.5
    grades = [incline_percent(v) for v in _values(edge.get("incline"))]
    if any(g is not None and g > SLOPE_CONCERN_PERCENT for g in grades):
        concerns.append("Mapped slope exceeds 8% model threshold")
        if name in {"wheelchair", "stroller"}:
            factor += 2.0
    if values(edge, "incline") & {"up", "down"}:
        concerns.append("Slope direction recorded; steepness unknown")
        missing.append("incline_grade")
    if name in {"wheelchair", "stroller"}:
        factor += 0.08 * len(missing)
        if not any(values(t, "wheelchair") & {"yes", "designated"} for t in places):
            factor += 0.1
    if name == "low_vision":
        for key in ("lit",):
            (known if values(edge, key) else missing).append(key)
        if "yes" not in values(edge, "lit"):
            factor += 0.15
        if crossing:
            for key in ("crossing:signals", "traffic_signals:sound"):
                (known if any(values(t, key) for t in places) else missing).append(key)
            if not any("yes" in values(t, "tactile_paving") for t in places):
                factor += 0.6
            if not any("yes" in values(t, "traffic_signals:sound") for t in places):
                factor += 0.6
            if not any(
                values(t, "crossing") & {"traffic_signals"}
                or "yes" in values(t, "crossing:signals")
                for t in places
            ):
                factor += 1.5
    if crossing and any(values(t, "crossing") & {"unmarked", "no"} for t in places):
        concerns.append("Mapped unmarked crossing")
        if name != "standard":
            factor += 2.5 if name == "low_vision" else 1.0
    if values(edge, "sidewalk") & {"no", "none"}:
        concerns.append("Mapped sidewalk=no; road walking may be involved")
    elif (
        name in {"wheelchair", "stroller"}
        and values(edge, "highway") & {"primary", "secondary", "trunk", "residential"}
        and not values(edge, "sidewalk")
    ):
        factor += 0.15
    reasons = concerns + [f"Missing {key.replace('_', ' ')}" for key in missing]
    status = "concern" if concerns else "unknown" if missing else "mapped"
    return True, factor, status, reasons, known
