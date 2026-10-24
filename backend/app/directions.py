"""Rider-facing walking maneuvers built from ordered, edge-level route segments.

The router returns one segment per directed graph edge. OpenStreetMap splits a
single sidewalk into many short ways (at driveways, curb nodes, crossings and
tag changes), so reporting every edge produced dozens of meaningless steps.
This module groups edges into maneuvers and only starts a new instruction when
the data supports a real navigation decision:

* the walker changes to a differently named street,
* the route turns at a junction where another mapped path is available,
* the route crosses a street at an angle to the direction of travel, or
* the route reaches stairs, an elevator or an unmapped connector.

A bend in a path with no alternative branch is not a turn. Street names are
used only when the OSM edge itself carries a ``name`` tag; sidewalks are never
given the name of a nearby road. Edge-level segments stay in the route result
and every maneuver records the segment range it covers, so the grouping can be
audited against the underlying data.
"""

from __future__ import annotations

from math import atan2, cos, degrees, radians, sin
from typing import Any

from .accessibility import _crossing_applies, _values, is_mapped_stairs
from .geospatial import distance_m

STRAIGHT_DEGREES = 30.0
SLIGHT_DEGREES = 60.0
SHARP_DEGREES = 140.0
U_TURN_DEGREES = 170.0
BEARING_WINDOW_M = 20.0
SHORT_MANEUVER_M = 12.0
# Crossing features this close together along the route describe one crossing
# (kerb nodes, a crossing node and its crosswalk edge, or a divided road).
CROSSING_CLUSTER_M = 20.0

LABELS = {
    "sidewalk": "the sidewalk",
    "path": "the walking path",
    "street": "the street",
    "service": "the service road",
    "platform": "the platform",
    "indoor": "the indoor walkway",
    "crossing": "the crosswalk",
    "steps": "the stairs",
    "elevator": "the elevator",
}

# Plain-language versions of documented concerns produced by profiles.assess().
CONCERN_TEXT = {
    "Mapped stairs": "The map shows stairs here.",
    "Mapped wheelchair=no": "The map marks this section as not wheelchair accessible.",
    "Mapped restrictive barrier": "The map shows a gate or barrier here.",
    "Mapped raised kerb at crossing": "The map shows a raised curb at this crossing.",
    "Mapped loose or uneven surface": "The map shows a loose or uneven surface here.",
    "Mapped poor smoothness": "The map shows a rough surface here.",
    "Mapped slope exceeds profile model concern threshold": "The map shows a steep slope here.",
    "Slope direction recorded; steepness unknown": "The map shows a slope here, but its steepness isn't recorded.",
    "Mapped sidewalk=no; road walking may be involved": "The map shows no sidewalk here, so the route may enter the road.",
    "Mapped passage is narrower than profile model minimum": "The map shows a narrow passage here.",
    "Mapped surface exceeds profile smoothness limit": "The map shows a very rough surface here.",
    "Mapped slope exceeds profile model limit": "The map shows a slope steeper than this travel option allows.",
}
CONNECTOR_NOTE = "We can't confirm there's a usable way through this section."

CONCERN_SUMMARY = {
    "Mapped stairs": "stairs",
    "Mapped wheelchair=no": "a section marked as not wheelchair accessible",
    "Mapped restrictive barrier": "a gate or barrier",
    "Mapped raised kerb at crossing": "a raised curb",
    "Mapped loose or uneven surface": "a loose or uneven surface",
    "Mapped poor smoothness": "a rough surface",
    "Mapped slope exceeds profile model concern threshold": "a steep slope",
    "Slope direction recorded; steepness unknown": "a slope with unknown steepness",
    "Mapped sidewalk=no; road walking may be involved": "a place where no sidewalk is recorded",
    "Mapped passage is narrower than profile model minimum": "a narrow passage",
    "Mapped surface exceeds profile smoothness limit": "a very rough surface",
    "Mapped slope exceeds profile model limit": "a slope steeper than this travel option allows",
}


# --------------------------------------------------------------------------- #
# Segment classification (called by the router with full OSM tags)
# --------------------------------------------------------------------------- #

def _lower(tags: dict[str, Any], key: str) -> set[str]:
    return {value.lower() for value in _values(tags.get(key))}


def segment_kind(edge: dict[str, Any]) -> str:
    highway = _lower(edge, "highway")
    footway = _lower(edge, "footway")
    if is_mapped_stairs(edge):
        return "steps"
    if "elevator" in highway:
        return "elevator"
    if "crossing" in footway or "crossing" in highway or (
        highway & {"footway", "path", "cycleway"} and _lower(edge, "crossing")
    ):
        return "crossing"
    if "sidewalk" in footway:
        return "sidewalk"
    if "platform" in highway or "platform" in _lower(edge, "railway") or "platform" in _lower(edge, "public_transport"):
        return "platform"
    if "corridor" in highway or "yes" in _lower(edge, "indoor"):
        return "indoor"
    if highway & {"footway", "path", "pedestrian", "cycleway", "bridleway", "track"}:
        return "path"
    if "service" in highway:
        return "service"
    return "street"


def crossing_type(*tags: dict[str, Any]) -> str:
    values: set[str] = set()
    signals = False
    for item in tags:
        values |= _lower(item, "crossing")
        signals = signals or "yes" in _lower(item, "crossing:signals") or "traffic_signals" in _lower(item, "highway")
    if values & {"unmarked", "no"}:
        return "unmarked"
    if signals or "traffic_signals" in values:
        return "signals"
    if values & {"marked", "zebra", "uncontrolled", "pelican", "toucan", "pegasus", "island"}:
        return "marked"
    return "unrecorded"


def node_crossing(node: dict[str, Any]) -> str | None:
    """Crossing type when a graph node is itself a mapped street crossing."""
    if "crossing" in _lower(node, "highway") or _lower(node, "crossing"):
        return crossing_type(node)
    return None


def describe_edge(edge: dict[str, Any], start: dict[str, Any], end: dict[str, Any]) -> dict[str, Any]:
    kind = segment_kind(edge)
    return {
        "kind": kind,
        "highway": " / ".join(_values(edge.get("highway"))) or None,
        "crossing": crossing_type(edge, start, end) if kind == "crossing" and _crossing_applies(edge, start, end) else None,
        "end_node_crossing": None if kind == "crossing" else node_crossing(end),
    }


# --------------------------------------------------------------------------- #
# Geometry helpers
# --------------------------------------------------------------------------- #

def _bearing(a: list[float], b: list[float]) -> float:
    lat1, lat2, delta = radians(a[1]), radians(b[1]), radians(b[0] - a[0])
    return (degrees(atan2(sin(delta) * cos(lat2), cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(delta))) + 360) % 360


def _signed_delta(before: float, after: float) -> float:
    return (after - before + 540) % 360 - 180


class _Polyline:
    """The whole route as one measured line, with each segment's start offset."""

    def __init__(self, segments: list[dict[str, Any]]):
        self.points: list[list[float]] = []
        self.offsets: list[float] = []
        self.boundaries: list[float] = []
        travelled = 0.0
        for segment in segments:
            coords = segment["geometry"]["coordinates"]
            self.boundaries.append(travelled)
            for index, point in enumerate(coords):
                if self.points and index == 0 and point == self.points[-1]:
                    continue
                if self.points:
                    travelled += distance_m((self.points[-1][1], self.points[-1][0]), (point[1], point[0]))
                self.points.append([float(point[0]), float(point[1])])
                self.offsets.append(travelled)
        self.boundaries.append(travelled)
        self.length = travelled

    def at(self, offset: float) -> list[float]:
        offset = max(0.0, min(self.length, offset))
        for index in range(1, len(self.points)):
            if self.offsets[index] >= offset:
                span = self.offsets[index] - self.offsets[index - 1]
                if span <= 0:
                    return self.points[index]
                t = (offset - self.offsets[index - 1]) / span
                a, b = self.points[index - 1], self.points[index]
                return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
        return self.points[-1]

    def heading(self, start: float, end: float) -> float | None:
        a, b = self.at(start), self.at(end)
        if distance_m((a[1], a[0]), (b[1], b[0])) < 0.5:
            return None
        return _bearing(a, b)

    def turn_at(self, boundary: float, window: float = BEARING_WINDOW_M) -> float:
        """Signed turn angle using approach/departure geometry around a point."""
        approach = self.heading(boundary - window, boundary)
        departure = self.heading(boundary, boundary + window)
        if approach is None or departure is None:
            return 0.0
        return _signed_delta(approach, departure)


# --------------------------------------------------------------------------- #
# Grouping
# --------------------------------------------------------------------------- #

def _kind(segment: dict[str, Any]) -> str:
    if "connector" in str(segment.get("source", "")).lower():
        return "connector"
    return segment.get("kind") or ("street" if segment.get("name") else "path")


def _is_hard(kind: str) -> bool:
    return kind in {"connector", "steps", "elevator"}


def _turn_kind(delta: float) -> str:
    size = abs(delta)
    side = "right" if delta > 0 else "left"
    if size < STRAIGHT_DEGREES:
        return "continue"
    if size < SLIGHT_DEGREES:
        return f"slight-{side}"
    if size < SHARP_DEGREES:
        return f"turn-{side}"
    if size < U_TURN_DEGREES:
        return f"sharp-{side}"
    return "u-turn"


def _break_between(previous: dict[str, Any], current: dict[str, Any], delta: float,
                   group_kinds: list[str], group_names: set[str]) -> bool:
    a, b = _kind(previous), _kind(current)
    if _is_hard(a) or _is_hard(b):
        return a != b or a == "connector"
    turning = abs(delta) >= STRAIGHT_DEGREES
    # A path that bends where no other mapped path meets is not a decision.
    degree = previous.get("end_junction_degree")
    junction = degree is None or degree >= 3
    if b == "crossing" and a != "crossing":
        return turning
    if a == "crossing" and b != "crossing":
        # Leaving a crosswalk straight ahead continues the same maneuver.
        return turning and junction
    name_a, name_b = previous.get("name"), current.get("name")
    if name_b and group_names and name_b not in group_names:
        return True
    if name_a and name_a == name_b:
        # Following the same named street around a bend is not a new step;
        # only a real turn at a junction needs one ("to stay on").
        return abs(delta) >= SLIGHT_DEGREES and junction
    if name_a and not name_b and b in {"street", "service"} and turning:
        return True
    return turning and junction


def _group(segments: list[dict[str, Any]], line: _Polyline) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for index, segment in enumerate(segments):
        if not groups:
            groups.append({"segments": [index], "turn": None})
            continue
        current = groups[-1]
        previous = segments[index - 1]
        delta = line.turn_at(line.boundaries[index])
        kinds = [_kind(segments[i]) for i in current["segments"]]
        names = {segments[i]["name"] for i in current["segments"] if segments[i].get("name")}
        if _break_between(previous, segment, delta, kinds, names):
            groups.append({"segments": [index], "turn": delta})
        else:
            current["segments"].append(index)
    return groups


def _length(segments: list[dict[str, Any]], group: dict[str, Any]) -> float:
    return sum(float(segments[i]["length_m"]) for i in group["segments"])


def _critical(segments: list[dict[str, Any]], group: dict[str, Any]) -> bool:
    for i in group["segments"]:
        segment = segments[i]
        if _is_hard(_kind(segment)) or _kind(segment) == "crossing":
            return True
        if any(not reason.startswith("Missing ") and reason != "Mapped unmarked crossing"
               for reason in segment.get("reasons", [])):
            return True
    return False


def _merge_short(segments: list[dict[str, Any]], groups: list[dict[str, Any]], line: _Polyline) -> list[dict[str, Any]]:
    """Absorb tiny jogs (e.g. a few meters between two sidewalk ways) that
    would otherwise read as 'turn left, then immediately turn right'."""
    changed = True
    while changed:
        changed = False
        for position in range(1, len(groups)):
            group = groups[position]
            if _length(segments, group) >= SHORT_MANEUVER_M or _critical(segments, group):
                continue
            previous = groups[position - 1]
            if _kind(segments[previous["segments"][-1]]) == "connector":
                continue
            previous["segments"].extend(group["segments"])
            del groups[position]
            if position < len(groups):
                following = groups[position]
                boundary = line.boundaries[following["segments"][0]]
                # Re-measure the next decision across the absorbed jog.
                window = max(BEARING_WINDOW_M, _length(segments, group) + BEARING_WINDOW_M)
                following["turn"] = line.turn_at(boundary, window)
                if not _critical(segments, following) and abs(following["turn"]) < STRAIGHT_DEGREES:
                    names = {segments[i].get("name") for i in previous["segments"] if segments[i].get("name")}
                    following_names = {segments[i].get("name") for i in following["segments"] if segments[i].get("name")}
                    if not following_names or not names or following_names & names:
                        previous["segments"].extend(following["segments"])
                        del groups[position]
            changed = True
            break
    return groups


# --------------------------------------------------------------------------- #
# Instruction text
# --------------------------------------------------------------------------- #

CARDINALS = ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"]


def _dominant(segments: list[dict[str, Any]], indexes: list[int]) -> tuple[str | None, str]:
    """Return (name, kind) covering most of the walked distance in a group."""
    walking = [i for i in indexes if _kind(segments[i]) not in {"crossing", "connector"}] or indexes
    total = sum(float(segments[i]["length_m"]) for i in walking) or 1.0
    by_name: dict[str, float] = {}
    by_kind: dict[str, float] = {}
    for i in walking:
        length = float(segments[i]["length_m"])
        if segments[i].get("name"):
            by_name[segments[i]["name"]] = by_name.get(segments[i]["name"], 0.0) + length
        by_kind[_kind(segments[i])] = by_kind.get(_kind(segments[i]), 0.0) + length
    name = max(by_name, key=by_name.get) if by_name else None
    if name and by_name[name] / total < 0.5:
        name = None
    return name, max(by_kind, key=by_kind.get)


def _target(name: str | None, kind: str, onto: bool) -> str:
    if name:
        return f"{'onto' if onto else 'on'} {name}"
    return f"{'onto' if onto else 'along'} {LABELS.get(kind, 'the path')}"


def _turn_phrase(turn: str) -> str:
    if turn in {"continue", "depart"}:
        return "Continue"
    if turn == "u-turn":
        return "Turn around"
    size, side = turn.split("-")
    return {"slight": "Keep", "turn": "Turn", "sharp": "Turn sharply"}[size] + " " + side


CROSSING_PRIORITY = {"unmarked": 0, "signals": 1, "marked": 2, "unrecorded": 3}


def _crossings(segments: list[dict[str, Any]], indexes: list[int], offsets: list[float]) -> list[str]:
    """One entry per crossing: crosswalk edges and crossing nodes within
    CROSSING_CLUSTER_M of each other along the route count once. When they
    disagree, an unmarked record wins, then any recorded type over none."""
    features: list[tuple[float, float, str]] = []
    for i in indexes:
        segment = segments[i]
        start, end = offsets[i], offsets[i] + float(segment["length_m"])
        if _kind(segment) == "crossing":
            features.append((start, end, segment.get("crossing") or "unrecorded"))
        elif segment.get("end_node_crossing"):
            features.append((end, end, segment["end_node_crossing"]))
    events: list[list[Any]] = []
    for start, end, kind in features:
        if events and start - events[-1][1] <= CROSSING_CLUSTER_M:
            events[-1][1] = max(events[-1][1], end)
            if CROSSING_PRIORITY[kind] < CROSSING_PRIORITY[events[-1][2]]:
                events[-1][2] = kind
        else:
            events.append([start, end, kind])
    return [event[2] for event in events]


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def _notes(segments: list[dict[str, Any]], indexes: list[int], leading_crossing: bool,
           offsets: list[float]) -> tuple[list[str], list[str], dict[str, int]]:
    events = _crossings(segments, indexes, offsets)
    counts = {
        "total": len(events),
        "unmarked": events.count("unmarked"),
        "signals": events.count("signals"),
        "marked": events.count("marked"),
        "unrecorded": events.count("unrecorded"),
    }
    notes: list[str] = []
    passing = events[1:] if leading_crossing else events
    if leading_crossing and events:
        first = events[0]
        notes.append({
            "unmarked": "The map shows no marked crosswalk at this crossing.",
            "signals": "Traffic signals are recorded at this crossing.",
            "marked": "The map shows a marked crosswalk here.",
            "unrecorded": "The map doesn't say what kind of crossing this is.",
        }[first])
    if passing:
        unmarked = passing.count("unmarked")
        text = f"{_plural(len(passing), 'crossing')} {'is' if len(passing) == 1 else 'are'} along this part of the route"
        if unmarked:
            text += f". {_plural(unmarked, 'crossing')} {'has' if unmarked == 1 else 'have'} no marked crosswalk recorded on the map"
        unrecorded = passing.count("unrecorded")
        if unrecorded:
            text += f". {_plural(unrecorded, 'crossing')} {'has' if unrecorded == 1 else 'have'} no crossing type recorded on the map"
        notes.append(text + ".")
    concerns: list[str] = []
    for i in indexes:
        for reason in segments[i].get("reasons", []):
            if reason.startswith("Missing ") or reason == "Mapped unmarked crossing" or reason in concerns:
                continue
            if reason.startswith("Off-network connector"):
                continue
            concerns.append(reason)
    return notes, concerns, counts


def _cardinal(heading: float) -> str:
    return CARDINALS[int((heading + 22.5) / 45) % 8]


def _curve_phrase(line: _Polyline, indexes: list[int], distance: float) -> str:
    """Mention a forced bend inside a step ("then follow it as it curves
    north") so the next step's turn reads correctly. Measured from geometry."""
    if distance < 60:
        return ""
    start = line.boundaries[indexes[0]]
    end = line.boundaries[indexes[-1] + 1]
    first = line.heading(start, start + 30)
    last = line.heading(end - 30, end)
    if first is None or last is None or abs(_signed_delta(first, last)) < 60:
        return ""
    if _cardinal(first) == _cardinal(last):
        return ""
    return f", then follow it as it curves {_cardinal(last)}"


def _status(segments: list[dict[str, Any]], indexes: list[int]) -> str:
    statuses = {segments[i].get("status") for i in indexes}
    for status in ("concern", "unknown", "mapped"):
        if status in statuses:
            return status
    return "unknown"


def directions(segments: list[dict[str, Any]], destination: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Maneuvers derived from ordered edge geometry and topology.

    Never invents a street name, a turn or a usable connection."""
    usable = [s for s in segments if len(s.get("geometry", {}).get("coordinates", [])) >= 2]
    if not usable:
        return []
    line = _Polyline(usable)
    groups = _merge_short(usable, _group(usable, line), line)
    offsets: list[float] = []
    travelled = 0.0
    for segment in usable:
        offsets.append(travelled)
        travelled += float(segment["length_m"])
    previous_name: str | None = None
    result: list[dict[str, Any]] = []
    walked_any = False
    for position, group in enumerate(groups):
        indexes = group["segments"]
        first = usable[indexes[0]]
        kind = _kind(first)
        distance = round(sum(float(usable[i]["length_m"]) for i in indexes), 2)
        name, dominant_kind = _dominant(usable, indexes)
        turn = "depart" if group["turn"] is None else _turn_kind(group["turn"])
        leading_crossing = kind == "crossing"
        notes, concerns, crossings = _notes(usable, indexes, leading_crossing, offsets)
        missing = sorted({reason[len("Missing "):] for i in indexes for reason in usable[i].get("reasons", [])
                          if reason.startswith("Missing ")})
        if kind == "connector":
            is_last = position == len(groups) - 1
            stop = (destination or {}).get("stop_name")
            instruction = (
                f"No walking-path data is available between the last path shown on the map and {stop}" if is_last and stop
                else "No walking-path data is available between the last path shown on the map and your destination" if is_last
                else "No walking-path data is available between your start and the nearest path shown on the map"
            )
            maneuver = "connector"
            notes = [CONNECTOR_NOTE]
        elif kind in {"steps", "elevator"}:
            verb = "Take the stairs" if kind == "steps" else "Take the elevator"
            prefix = "" if turn in {"depart", "continue"} else f"{_turn_phrase(turn)} and "
            instruction = prefix + (verb[0].lower() + verb[1:] if prefix else verb)
            maneuver = kind
        elif leading_crossing:
            prefix = "" if turn in {"depart", "continue"} else f"{_turn_phrase(turn)} and "
            instruction = prefix + ("cross the street" if prefix else "Cross the street")
            rest = [i for i in indexes if _kind(usable[i]) != "crossing"]
            if rest:
                instruction += f", then continue {_target(name, dominant_kind, onto=bool(name))}"
            maneuver = "cross"
        elif not walked_any:
            heading = line.heading(line.boundaries[indexes[0]], line.boundaries[indexes[0]] + min(30.0, distance)) or 0.0
            instruction = f"Head {CARDINALS[int((heading + 22.5) / 45) % 8]} {_target(name, dominant_kind, onto=False)}"
            maneuver = "depart"
        elif name and name == previous_name:
            instruction = f"{_turn_phrase(turn)} to stay on {name}"
            maneuver = turn
        else:
            onto = turn != "continue" or bool(name)
            instruction = f"{_turn_phrase(turn)} {_target(name, dominant_kind, onto=onto)}"
            if not name:
                # Unnamed sidewalks look alike; a compass heading from the
                # geometry tells consecutive steps apart without inventing names.
                start_offset = line.boundaries[indexes[0]]
                heading = line.heading(start_offset, start_offset + min(30.0, distance))
                if heading is not None:
                    instruction += f" heading {CARDINALS[int((heading + 22.5) / 45) % 8]}"
            maneuver = turn
        if maneuver not in {"connector", "steps", "elevator", "cross"}:
            instruction += _curve_phrase(line, indexes, distance)
        if kind != "connector":
            walked_any = True
            previous_name = name
        start = first["geometry"]["coordinates"][0]
        result.append({
            "instruction": instruction,
            "distance_m": distance,
            "status": _status(usable, indexes),
            "warnings": [CONNECTOR_NOTE] if kind == "connector" else [CONCERN_TEXT.get(c, c) for c in concerns],
            "notes": notes,
            "maneuver": maneuver,
            "kind": "connector" if kind == "connector" else ("crossing" if leading_crossing else dominant_kind),
            "name": name,
            "documented_concerns": concerns,
            "missing_information": missing,
            "crossings": crossings,
            "segment_range": [indexes[0], indexes[-1]],
            "segment_count": len(indexes),
            "location": [round(start[0], 7), round(start[1], 7)],
        })
    if destination and destination.get("stop_name"):
        end = usable[-1]["geometry"]["coordinates"][-1]
        result.append({
            "instruction": f"Arrive at {destination['stop_name']}",
            "distance_m": 0.0,
            "status": "mapped",
            "warnings": [],
            "notes": [],
            "maneuver": "arrive",
            "kind": "arrive",
            "name": None,
            "documented_concerns": [],
            "missing_information": [],
            "crossings": {"total": 0, "unmarked": 0, "signals": 0, "marked": 0, "unrecorded": 0},
            "segment_range": None,
            "segment_count": 0,
            "location": [round(end[0], 7), round(end[1], 7)],
        })
    return result


# --------------------------------------------------------------------------- #
# Route-level summaries
# --------------------------------------------------------------------------- #

ATTRIBUTE_TEXT = {
    "surface": "surface type",
    "smoothness": "surface condition",
    "incline": "slope",
    "width": "path width",
    "wheelchair": "wheelchair access",
    "kerb": "curb ramps",
    "crossing": "crossing type",
    "tactile paving": "tactile paving",
    "tactile_paving": "tactile paving",
    "sidewalk": "sidewalk presence",
    "lit": "lighting",
    "crossing:signals": "crossing signals",
    "traffic signals:sound": "audible signals",
}


def accessibility_summary(segments: list[dict[str, Any]], maneuvers: list[dict[str, Any]],
                          route_distance_m: float) -> dict[str, Any]:
    """One concise rider-facing summary; details point back to steps/segments."""
    restrictions: dict[str, dict[str, Any]] = {}
    for number, step in enumerate(maneuvers, start=1):
        for concern in step.get("documented_concerns", []):
            item = restrictions.setdefault(concern, {
                "code": concern,
                "text": CONCERN_TEXT.get(concern, concern),
                "steps": [],
                "locations": [],
            })
            item["steps"].append(number)
            name = step.get("name")
            if name and name not in item["locations"]:
                item["locations"].append(name)
    missing_distance: dict[str, float] = {}
    walked = 0.0
    connectors = []
    for index, segment in enumerate(segments):
        length = float(segment["length_m"])
        if _kind(segment) == "connector":
            connectors.append({"segment": index, "distance_m": round(length, 1),
                               "position": "start" if index == 0 else "end"})
            continue
        walked += length
        for reason in segment.get("reasons", []):
            if reason.startswith("Missing "):
                key = reason[len("Missing "):]
                missing_distance[key] = missing_distance.get(key, 0.0) + length
    missing = sorted((
        {"attribute": key, "label": ATTRIBUTE_TEXT.get(key, key),
         "distance_m": round(value, 1), "share": round(value / walked, 3) if walked else None}
        for key, value in missing_distance.items()
    ), key=lambda item: -item["distance_m"])
    crossing_total = sum(step.get("crossings", {}).get("total", 0) for step in maneuvers)
    unmarked = sum(step.get("crossings", {}).get("unmarked", 0) for step in maneuvers)
    unrecorded = sum(step.get("crossings", {}).get("unrecorded", 0) for step in maneuvers)
    lines = []
    if restrictions:
        concerns = []
        for item in restrictions.values():
            subject = CONCERN_SUMMARY.get(item["code"], "an accessibility concern")
            location = ", ".join(item["locations"])
            concerns.append(f"{subject} near {location}" if location else f"{subject} along this route")
        if len(concerns) == 1:
            lines.append(f"Map data shows {concerns[0]}.")
        else:
            lines.append(f"Map data shows these possible accessibility concerns: {'; '.join(concerns)}.")
    if missing:
        lines.append("Some walking paths on this route have no accessibility details recorded on the map.")
    if unmarked:
        lines.append(f"{_plural(unmarked, 'crossing')} {'has' if unmarked == 1 else 'have'} no marked crosswalk recorded on the map.")
    if unrecorded:
        lines.append(f"{_plural(unrecorded, 'crossing')} {'has' if unrecorded == 1 else 'have'} no crossing type recorded on the map.")
    if connectors:
        total = sum(c["distance_m"] for c in connectors)
        positions = {connector["position"] for connector in connectors}
        location = "near your start and destination" if len(positions) == 2 else "near your start" if "start" in positions else "near your destination"
        lines.append(f"About {round(total * 3.28084 / 10) * 10 or 10} ft {location} has no walking-path data.")
    return {
        "headline": lines[0] if lines else "No known accessibility concerns are recorded in the map data. This doesn't confirm the route is accessible.",
        "lines": lines,
        "documented_restrictions": list(restrictions.values()),
        "missing_information": missing,
        "crossings": {"total": crossing_total, "unmarked": unmarked, "unrecorded_type": unrecorded},
        "unmapped_connectors": connectors,
        "walking_distance_m": round(route_distance_m, 1),
        "interpretation": "Missing information is unknown. It does not show that a route is accessible or inaccessible.",
    }


def geometry_audit(segments: list[dict[str, Any]]) -> dict[str, Any]:
    """Checks used by tests and the evidence view: continuity, reversals and connectors."""
    gaps = []
    reversals = []
    usable = [s for s in segments if len(s.get("geometry", {}).get("coordinates", [])) >= 2]
    for index in range(1, len(usable)):
        previous_end = usable[index - 1]["geometry"]["coordinates"][-1]
        start = usable[index]["geometry"]["coordinates"][0]
        gap = distance_m((previous_end[1], previous_end[0]), (start[1], start[0]))
        if gap > 0.5:
            gaps.append({"segment": index, "gap_m": round(gap, 2)})
    if usable:
        line = _Polyline(usable)
        for index in range(1, len(usable)):
            if min(float(usable[index - 1]["length_m"]), float(usable[index]["length_m"])) < 3:
                continue
            delta = line.turn_at(line.boundaries[index], 8.0)
            if abs(delta) >= U_TURN_DEGREES:
                reversals.append({"segment": index, "turn_degrees": round(delta, 1)})
    return {
        "continuous": not gaps,
        "gaps": gaps,
        "reversals": reversals,
        "unmapped_connector_m": round(sum(float(s["length_m"]) for s in usable if _kind(s) == "connector"), 1),
    }
