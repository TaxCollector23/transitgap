import type { Stop } from "./types";

export const METERS_PER_MILE = 1609.344;
const FEET_PER_METER = 3.28084;

/** Feet for walking-scale distances, miles beyond ~1,000 ft. Never rounds a
 * real, nonzero distance down to zero. */
export function formatDistance(meters: number) {
  const feet = meters * FEET_PER_METER;
  if (feet < 50) return `${Math.max(5, Math.round(feet / 5) * 5)} ft`;
  if (feet < 1000) return `${Math.round(feet / 10) * 10} ft`;
  const miles = meters / METERS_PER_MILE;
  return `${miles < 10 ? miles.toFixed(1) : Math.round(miles)} mi`;
}

export function spokenDistance(meters: number) {
  return formatDistance(meters)
    .replace(/ ft$/, " feet")
    .replace(/^1\.0 mi$/, "1 mile")
    .replace(/ mi$/, " miles");
}

export function formatDuration(seconds: number) {
  const minutes = Math.max(1, Math.round(seconds / 60));
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} hr ${minutes % 60} min`;
}

export const PROFILES = [
  { value: "standard", label: "Walking" },
  { value: "wheelchair", label: "Wheelchair" },
  { value: "stroller", label: "Stroller" },
  { value: "low_vision", label: "Low vision" },
] as const;

export function profileLabel(value: string) {
  if (value === "prefer_documented_paths") return "Prefer documented paths";
  return PROFILES.find((p) => p.value === value)?.label || value;
}

export type AgencyFilter = "all" | "vta" | "caltrain" | "bart";

export function agencyOf(stop: Stop): Exclude<AgencyFilter, "all"> {
  const value = (stop.agency || stop.agency_name || "vta").toLowerCase();
  return value === "caltrain" || value === "bart" ? value : "vta";
}

export function agencyName(stop: Stop) {
  return stop.agency_name || "VTA";
}

/** A searchable destination: a station (all its platforms) or a single stop. */
export type Place = {
  key: string;
  name: string;
  agency: Exclude<AgencyFilter, "all">;
  description: string;
  stops: Stop[];
  latitude: number;
  longitude: number;
};

function kindLabel(stops: Stop[], agency: Place["agency"], station: boolean) {
  const modes = new Set(stops.flatMap((s) => s.modes || []));
  if (agency === "bart") return "BART station";
  if (agency === "caltrain")
    return modes.size && !modes.has("rail") && modes.has("bus")
      ? "Caltrain shuttle stop"
      : "Caltrain station";
  if (modes.has("light_rail"))
    return station ? "VTA light rail station" : "VTA light rail platform";
  if (modes.has("bus")) return "VTA bus stop";
  return station ? "VTA station" : "VTA stop";
}

export function buildPlaces(stops: Stop[]): Place[] {
  const groups = new Map<string, Stop[]>();
  for (const stop of stops) {
    // Group platforms that are only told apart by direction or number (Caltrain
    // northbound/southbound, BART platform 1/2). Stops with their own names,
    // such as "San Jose Diridon (Bay 11)", stay separate: the bay matters.
    const groupable = stop.station_id && (stop.platform_name || stop.stop_name === stop.station_name);
    const key = groupable ? `station:${stop.station_id}` : `stop:${stop.stop_id}`;
    groups.set(key, [...(groups.get(key) || []), stop]);
  }
  return [...groups.entries()].map(([key, members]) => {
    const first = members[0];
    const agency = agencyOf(first);
    const station = key.startsWith("station:");
    return {
      key,
      name: (station && first.station_name) || first.stop_name,
      agency,
      description: kindLabel(members, agency, station),
      stops: members,
      latitude: members.reduce((sum, s) => sum + s.latitude, 0) / members.length,
      longitude: members.reduce((sum, s) => sum + s.longitude, 0) / members.length,
    };
  });
}

export function distanceM(a: [number, number], b: [number, number]) {
  const rad = (value: number) => (value * Math.PI) / 180;
  const dLat = rad(b[0] - a[0]);
  const dLon = rad(b[1] - a[1]);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(rad(a[0])) * Math.cos(rad(b[0])) * Math.sin(dLon / 2) ** 2;
  return 6371000 * 2 * Math.asin(Math.sqrt(h));
}

export function normalize(text: string) {
  return text.toLocaleLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

/** The platform of a place closest to a point (the route still ends at a
 * recorded entrance when the feed has one). */
export function nearestStop(place: Place, point: [number, number] | null) {
  if (!point || place.stops.length === 1) return place.stops[0];
  return [...place.stops].sort(
    (a, b) =>
      distanceM(point, [a.latitude, a.longitude]) -
      distanceM(point, [b.latitude, b.longitude]),
  )[0];
}
