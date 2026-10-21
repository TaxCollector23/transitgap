"""Explicit mobility model assumptions; source tags are not field verification.

All costs stay at least physical distance, preserving the geographic A* bound.
Limits below are configurable engineering assumptions, not legal/safety ratings.
Unknown measurements stay unknown and add a documented distance-scaled penalty.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import re
from .accessibility import _values, _crossing_applies, is_mapped_stairs

SLOPE_CONCERN_PERCENT = 8.0
ROUGH_SURFACES = {"gravel", "unpaved", "dirt", "grass", "sett", "cobblestone", "sand"}
ROUGH_SMOOTHNESS = {"bad", "very_bad", "horrible", "very_horrible", "impassable"}
IMPASSABLE_BARRIERS = {"kissing_gate", "stile", "turnstile"}
SPEED_MPS = {"standard":1.2,"wheelchair":0.9,"avoid_mapped_stairs":0.9,"stroller":0.9,"low_vision":1.2,"prefer_documented_paths":1.2}
OBJECTIVES = {
    "standard":"Minimize mapped walking distance",
    "wheelchair":"Exclude mapped stairs, wheelchair restrictions, impassable surfaces, narrow passages and excessive slopes; prefer documented paths",
    "avoid_mapped_stairs":"Wheelchair profile (legacy alias)",
    "stroller":"Exclude mapped stairs, impassable surfaces and restrictive passages; apply stroller-specific width, slope and surface assumptions",
    "low_vision":"Prefer recorded tactile paving, audible crossing signals and lighting; unknown crossings remain uncertain",
    "prefer_documented_paths":"Minimize distance weighted by missing applicable map attributes",
}

@dataclass(frozen=True)
class MobilityRules:
    minimum_width_m: float
    maximum_incline_percent: float
    slope_concern_percent: float
    rough_surface_extra: float
    poor_smoothness_extra: float
    slope_extra: float
    unknown_attribute_extra: float
    blocked_smoothness: frozenset[str]

RULES = {
    "wheelchair":MobilityRules(.80,12,8,1.5,1.5,2,.08,frozenset({"very_horrible","impassable"})),
    "stroller":MobilityRules(.55,15,10,1, .8,1,.05,frozenset({"impassable"})),
}

def values(tags, key):
    return {v.lower() for v in _values(tags.get(key))}

def incline_percent(value):
    if value is None or isinstance(value,(list,tuple)):
        return None
    match=re.fullmatch(r"\s*([+-]?\d+(?:\.\d+)?)\s*%?\s*",str(value))
    return abs(float(match[1])) if match else None

def width_m(value):
    if value is None or isinstance(value,(list,tuple)):
        return None
    match=re.fullmatch(r"\s*((?:\d+(?:\.\d+)?|\.\d+))\s*(m|cm|ft|')?\s*",str(value))
    if not match:
        return None
    return float(match[1])*({"cm":.01,"ft":.3048,"'":.3048}.get(match[2],1))

@dataclass(frozen=True)
class EdgeEvaluation:
    eligible: bool
    difficulty_multiplier: float
    uncertainty_multiplier: float
    status: str
    reasons: tuple[str,...]
    documented: tuple[str,...]
    missing: tuple[str,...]

    @property
    def multiplier(self):
        return self.difficulty_multiplier+self.uncertainty_multiplier

    def costs(self, distance):
        return {"physical_distance_m":distance,"difficulty_cost_m":distance*(self.difficulty_multiplier-1),"uncertainty_cost_m":distance*self.uncertainty_multiplier,"optimization_cost_m":distance*self.multiplier}


def assess(edge, start, end, profile):
    name=getattr(profile,"value",profile)
    if name=="avoid_mapped_stairs":name="wheelchair"
    if name not in OBJECTIVES:raise ValueError(f"Unsupported mobility profile: {name}")
    places=(edge,start,end)
    crossing=_crossing_applies(edge,start,end)
    concerns=[]
    exclusions=[]
    rules=RULES.get(name)
    if is_mapped_stairs(edge):
        concerns.append("Mapped stairs")
        if rules:exclusions.append("Mapped stairs")
    if any("no" in values(t,"wheelchair") for t in places):
        concerns.append("Mapped wheelchair=no")
        if name=="wheelchair":exclusions.append("Mapped wheelchair=no")
    if any(values(t,"barrier") & IMPASSABLE_BARRIERS for t in places):
        concerns.append("Mapped restrictive barrier")
        if rules:exclusions.append("Mapped restrictive barrier")
    if crossing and any("raised" in values(t,"kerb") for t in places):
        concerns.append("Mapped raised kerb at crossing")
        if name=="wheelchair":exclusions.append("Mapped raised kerb at crossing")
    known=[]; missing=[]
    for key in ("surface","smoothness","incline","width"):
        documented=bool(values(edge,key))
        if key=="incline":documented=any(incline_percent(v) is not None for v in _values(edge.get(key)))
        if key=="width":documented=any(width_m(v) is not None for v in _values(edge.get(key)))
        (known if documented else missing).append(key)
    if crossing:
        for key in ("kerb","crossing","tactile_paving"):
            (known if any(values(t,key) for t in places) else missing).append(key)
    difficulty=1.0; uncertainty=0.0
    if values(edge,"surface") & ROUGH_SURFACES:
        concerns.append("Mapped loose or uneven surface")
        if rules:difficulty+=rules.rough_surface_extra
    if values(edge,"smoothness") & ROUGH_SMOOTHNESS:
        concerns.append("Mapped poor smoothness")
        if rules:
            difficulty+=rules.poor_smoothness_extra
            if values(edge,"smoothness") & rules.blocked_smoothness:exclusions.append("Mapped surface exceeds profile smoothness limit")
    grades=[incline_percent(v) for v in _values(edge.get("incline"))]
    grade=max((g for g in grades if g is not None),default=None)
    if grade is not None and grade>(rules.slope_concern_percent if rules else SLOPE_CONCERN_PERCENT):
        concerns.append("Mapped slope exceeds profile model concern threshold")
        if rules:
            difficulty+=rules.slope_extra
            if grade>rules.maximum_incline_percent:exclusions.append("Mapped slope exceeds profile model limit")
    if values(edge,"incline") & {"up","down"}:
        concerns.append("Slope direction recorded; steepness unknown")
    if rules:
        widths=[width_m(v) for t in places for v in _values(t.get("width"))]
        if any(w is not None and w<rules.minimum_width_m for w in widths):
            exclusions.append("Mapped passage is narrower than profile model minimum")
        if crossing and name=="stroller" and any("raised" in values(t,"kerb") for t in places):difficulty+=.5
        uncertainty+=rules.unknown_attribute_extra*len(missing)
        if name=="wheelchair" and not any(values(t,"wheelchair") & {"yes","designated"} for t in places):uncertainty+=.1
    if name=="low_vision":
        (known if values(edge,"lit") else missing).append("lit")
        if "yes" not in values(edge,"lit"):uncertainty+=.15
        if crossing:
            for key in ("crossing:signals","traffic_signals:sound"):
                (known if any(values(t,key) for t in places) else missing).append(key)
            # Preferences describe recorded infrastructure, never guaranteed safety.
            if not any("yes" in values(t,"tactile_paving") for t in places):uncertainty+=.6
            if not any("yes" in values(t,"traffic_signals:sound") for t in places):uncertainty+=.6
            if not any(values(t,"crossing") & {"traffic_signals"} or "yes" in values(t,"crossing:signals") for t in places):uncertainty+=1.5
    if crossing and any(values(t,"crossing") & {"unmarked","no"} for t in places):
        concerns.append("Mapped unmarked crossing")
        if name!="standard":difficulty+=2.5 if name=="low_vision" else 1
    if values(edge,"sidewalk") & {"no","none"}:concerns.append("Mapped sidewalk=no; road walking may be involved")
    elif rules and values(edge,"highway") & {"primary","secondary","trunk","residential"} and not values(edge,"sidewalk"):uncertainty+=.15
    reasons=tuple(dict.fromkeys(exclusions+concerns+[f"Missing {k.replace('_',' ')}" for k in missing]))
    status="concern" if exclusions or concerns else "unknown" if missing else "mapped"
    return EdgeEvaluation(not exclusions,difficulty,uncertainty,status,reasons,tuple(known),tuple(missing))


def evaluate(edge,start,end,profile):
    result=assess(edge,start,end,profile)
    return result.eligible,result.multiplier,result.status,list(result.reasons),list(result.documented)


def configuration():
    return {name:{**asdict(rule),"blocked_smoothness":sorted(rule.blocked_smoothness)} for name,rule in RULES.items()}
