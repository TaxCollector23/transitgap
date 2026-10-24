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
  duplicateName: boolean;
  disambiguation: string;
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
  const places = [...groups.entries()].map(([key, members]) => {
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
      duplicateName: false,
      disambiguation: "",
    };
  });
  const byName = new Map<string, Place[]>();
  for (const place of places) {
    const key = normalize(place.name);
    byName.set(key, [...(byName.get(key) || []), place]);
  }
  return places.map((place) => {
    const matching = byName.get(normalize(place.name)) || [];
    if (matching.length < 2) return place;
    const details = baseDisambiguation(place);
    const signature = details.join("|");
    const sameDetail = matching.filter((candidate) => baseDisambiguation(candidate).join("|") === signature);
    const locationDetail = sameDetail.length > 1 ? relativeStopLocation(place, sameDetail) : "";
    return {
      ...place,
      duplicateName: true,
      disambiguation: [...details, locationDetail].filter(Boolean).join(" · "),
    };
  });
}

function unique(values: Array<string | null | undefined>) {
  return [...new Set(values.map((value) => value?.trim()).filter((value): value is string => Boolean(value)))];
}

function shortRoutes(stops: Stop[]) {
  const routes = unique(stops.flatMap((stop) => stop.routes_served || []));
  return routes.length
    ? `Routes ${routes.slice(0, 4).join(", ")}${routes.length > 4 ? ` and ${routes.length - 4} more` : ""}`
    : "Routes not listed in agency data";
}

function baseDisambiguation(place: Place) {
  const directions = unique(place.stops.map((stop) => stop.direction));
  const headsigns = unique(place.stops.flatMap((stop) => stop.headsigns || []));
  const platforms = unique(place.stops.map((stop) => stop.platform_name));
  const details: string[] = [];
  if (directions.length) details.push(directions.join(" / "));
  else if (headsigns.length) {
    const shown = headsigns.slice(0, 3).join(", ");
    details.push(`Agency trips head toward ${shown}${headsigns.length > 3 ? ` and ${headsigns.length - 3} more places` : ""}`);
  } else details.push("Direction not listed in agency data");
  if (platforms.length) details.push(`Bay or platform ${platforms.join(", ")}`);
  else details.push("Bay or platform not listed in agency data");
  details.push(shortRoutes(place.stops));
  const extraDescriptions = unique(place.stops
    .filter((stop) => !stop.direction)
    .map((stop) => stop.stop_description));
  if (extraDescriptions.length) details.push(`Agency stop detail: ${extraDescriptions.join(" / ")}`);
  return details;
}

function relativeStopLocation(place: Place, peers: Place[]) {
  const latitudeRange = Math.max(...peers.map((item) => item.latitude)) - Math.min(...peers.map((item) => item.latitude));
  const longitudeRange = Math.max(...peers.map((item) => item.longitude)) - Math.min(...peers.map((item) => item.longitude));
  if (latitudeRange < 0.000001 && longitudeRange < 0.000001) {
    const stopCode = unique(place.stops.map((stop) => stop.stop_code))[0];
    return stopCode ? `Agency stop code ${stopCode}` : "Agency data does not list a separate direction, platform, or location";
  }
  const useNorthSouth = latitudeRange >= longitudeRange;
  const sorted = [...peers].sort((a, b) => useNorthSouth ? a.latitude - b.latitude : a.longitude - b.longitude);
  const index = sorted.findIndex((item) => item.key === place.key);
  const low = useNorthSouth ? "south" : "west";
  const high = useNorthSouth ? "north" : "east";
  if (sorted.length === 2) return `${index === 0 ? low : high} of the other listed stop`;
  if (index === 0) return `the ${low}ernmost listed stop location`;
  if (index === sorted.length - 1) return `the ${high}ernmost listed stop location`;
  return `between the ${low}ern and ${high}ern listed stop locations`;
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

/** Compact feed-backed details that make nearby, similarly named stops distinct. */
export function placeSearchDetail(place: Place) {
  if (place.duplicateName) return [place.description, place.disambiguation].filter(Boolean).join(" · ");
  const platforms = [...new Set(place.stops.map((stop) => stop.platform_name).filter(Boolean))];
  const routes = [...new Set(place.stops.flatMap((stop) => stop.routes_served || []))];
  const details = [place.description];
  if (platforms.length) details.push(platforms.length === 1 ? platforms[0]! : `Platforms ${platforms.join(", ")}`);
  if (routes.length) details.push(`Routes ${routes.slice(0, 4).join(", ")}${routes.length > 4 ? ` +${routes.length - 4}` : ""}`);
  return details.join(" · ");
}

/** Short heading that preserves the feed-backed discriminator for duplicate names. */
export function placeHeading(place: Place) {
  const qualifier = place.duplicateName ? place.disambiguation.split(" · ")[0] : "";
  return qualifier ? `${place.name} — ${qualifier}` : place.name;
}
