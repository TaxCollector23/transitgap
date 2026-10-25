import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, ChevronDown, ChevronUp } from "lucide-react";
import { lazy, Suspense } from "react";
import OriginSearch from "./OriginSearch";
import StopSearch from "./StopSearch";
import RouteResult, { type Comparison } from "./RouteResult";
import type { GapDetail } from "./GapPanel";
const GapPanel = lazy(() => import("./GapPanel"));
const MapView = lazy(() => import("./MapView"));
const GroundTruthPanel = lazy(() => import("./GroundTruthPanel"));
import type { Coverage, ReachabilityAnalysis, RouteResult as Route, Stop } from "./types";
import { API, plannerData, PREPARED, warmRouting } from "./data";
import {
  PROFILES,
  type Place,
  buildPlaces,
  distanceM,
  formatDistance,
  formatDuration,
  nearestStop,
  profileLabel,
} from "./format";

const algorithms = [
  { value: "astar", label: "A*", description: "Uses distance to the stop to guide the search toward a lowest-cost route." },
  { value: "dijkstra", label: "Dijkstra", description: "Finds the lowest-cost route for your walking preference." },
  { value: "bidirectional_dijkstra", label: "Bidirectional Dijkstra", description: "Searches from both ends for the same lowest-cost objective." },
  { value: "bellman_ford", label: "Bellman–Ford", description: "Finds a lowest-cost route by relaxing edges. Usually slower on large networks." },
  { value: "breadth_first", label: "Breadth-first search", description: "Chooses the fewest network segments. The walking distance may be longer." },
];
type View = "route" | "advocates" | "report" | "methods";
type RouteKey = { origin: [number, number]; stopId: string; algorithm: string; profile: string };
type Problem = { message: string; retry?: () => void };
function initialView(): View {
  const requested = new URLSearchParams(location.search).get("view");
  if (requested === "gaps" || requested === "evidence" || requested === "advocates") return "advocates";
  return requested === "report" ? "report" : requested === "methods" ? "methods" : "route";
}
type ScheduleNotice = { message: string; agency: string; url: string };

const ROUTE_PROFILES = ["standard", "wheelchair", "stroller", "low_vision", "prefer_documented_paths"];
const SHARED_PROFILE_VALUES = new Set(ROUTE_PROFILES);

function initialProfile() {
  const shared = new URLSearchParams(location.search).get("profile");
  if (shared && SHARED_PROFILE_VALUES.has(shared)) return shared;
  try {
    const saved = localStorage.getItem("transitgap-profile-v1");
    if (saved && SHARED_PROFILE_VALUES.has(saved)) return saved;
  } catch {
    // Storage can be disabled; the planner still works with the default.
  }
  return "standard";
}

function feedDate(value?: string) {
  return value && /^\d{8}$/.test(value)
    ? `${value.slice(4, 6)}/${value.slice(6, 8)}/${value.slice(0, 4)}`
    : value || "not stated";
}

const CONNECTION_PROBLEM =
  "TransitGap is having trouble connecting. Your map is still available. Try again.";
const NO_ROUTE =
  "We couldn't calculate a route with the current map data. Try another stop or travel option.";

function insideRing(point: [number, number], ring: number[][]) {
  const [latitude, longitude] = point;
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    const crosses = yi > latitude !== yj > latitude && longitude < ((xj - xi) * (latitude - yi)) / (yj - yi) + xi;
    if (crosses) inside = !inside;
  }
  return inside;
}

function insideCoverage(point: [number, number], coverage: Coverage) {
  if (!coverage.boundary)
    return distanceM([coverage.center.latitude, coverage.center.longitude], point) <= coverage.radius_m;
  const polygons = coverage.boundary.type === "Polygon" ? [coverage.boundary.coordinates] : coverage.boundary.coordinates;
  return polygons.some(
    (polygon) => insideRing(point, polygon[0]) && !polygon.slice(1).some((ring) => insideRing(point, ring)),
  );
}

/** Plain-language versions of service failures. Never invents a cause. */
function routeProblem(status: number, detail: string) {
  if (status === 408) return "The route request did not finish within 12 seconds. Each walking-network search has a 3-second limit. Try again, or choose a different start or stop.";
  if (status === 503 || status >= 500 || status === 0) return CONNECTION_PROBLEM;
  if (/outside the supported area/i.test(detail)) return "That starting point is outside Santa Clara County. Choose a point inside the county boundary shown on the map.";
  if (/time limit|search exceeded.*limit|search.*\d+-second limit/i.test(detail)) return "The walking-network search reached its 3-second limit. Move the start to a street or sidewalk entrance, or try another transit stop.";
  if (/not connected to the mapped walking route/i.test(detail)) return "This start is not connected to the mapped walking route. Move the pin to a nearby street or sidewalk entrance and try again.";
  if (/from .* mapped (walking )?path|within .* of a mapped path/i.test(detail)) return "That starting point is too far from a mapped path. Choose a point on or near a street or sidewalk.";
  if (status === 404) return "That stop is no longer in the loaded transit data. Choose another stop.";
  if (status === 422) return NO_ROUTE;
  return "The route couldn't be calculated. Try again.";
}

function detailOf(data: unknown) {
  const detail = (data as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") return String((detail as { message?: string }).message || "");
  return "";
}

function waitForSignal<T>(promise: Promise<T>, signal: AbortSignal): Promise<T> {
  return new Promise((resolve, reject) => {
    const cleanup = () => signal.removeEventListener("abort", onAbort);
    const onAbort = () => {
      cleanup();
      reject(signal.reason || new Error("The request was cancelled."));
    };
    if (signal.aborted) return onAbort();
    signal.addEventListener("abort", onAbort, { once: true });
    promise.then(
      (value) => { cleanup(); resolve(value); },
      (error) => { cleanup(); reject(error); },
    );
  });
}

function coverageOutlinePath(coverage: Coverage | null) {
  if (!coverage?.boundary) return "";
  const polygons = coverage.boundary.type === "Polygon"
    ? [coverage.boundary.coordinates]
    : coverage.boundary.coordinates;
  const rings = polygons.map((polygon) => polygon[0]).filter((ring) => ring.length > 0);
  const points = rings.flat();
  if (!points.length) return "";
  const longitudes = points.map(([longitude]) => longitude);
  const latitudes = points.map(([, latitude]) => latitude);
  const west = Math.min(...longitudes), east = Math.max(...longitudes);
  const south = Math.min(...latitudes), north = Math.max(...latitudes);
  const width = Math.max(0.000001, east - west), height = Math.max(0.000001, north - south);
  return rings.map((ring) => ring.map(([longitude, latitude], index) => {
    const x = 2 + ((longitude - west) / width) * 52;
    const y = 34 - ((latitude - south) / height) * 32;
    return `${index ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(" ") + " Z").join(" ");
}

export default function App() {
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [stops, setStops] = useState<Stop[]>([]);
  const places = useMemo(() => buildPlaces(stops), [stops]);
  const [origin, setOrigin] = useState<[number, number] | null>(null);
  const [originLabel, setOriginLabel] = useState("");
  const [locating, setLocating] = useState(false);
  const [place, setPlace] = useState<Place | null>(null);
  const [algorithm, setAlgorithm] = useState("astar");
  const [profile, setProfile] = useState(initialProfile);
  const [view, setView] = useState<View>(initialView);
  const [editing, setEditing] = useState(false);
  const [recalculating, setRecalculating] = useState(false);
  const [study, setStudy] = useState<GapDetail | null>(null);
  const [reachabilityStudy, setReachabilityStudy] = useState<ReachabilityAnalysis | null>(null);
  const [reachabilityLayers, setReachabilityLayers] = useState({ documented: false, unknown: false });
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [comparing, setComparing] = useState(false);
  const [benchmark, setBenchmark] = useState<Array<{ algorithm: string; computation_time_ms?: number; distance_m?: number; error?: string }>>([]);
  const [benchmarking, setBenchmarking] = useState(false);
  const [result, setResult] = useState<Route | null>(null);
  const [resultKey, setResultKey] = useState<RouteKey | null>(null);
  const [loading, setLoading] = useState(true);
  const [mapReady, setMapReady] = useState(false);
  const [dataReady, setDataReady] = useState(false);
  const [routingWarm, setRoutingWarm] = useState(!PREPARED);
  const [warmingRouting, setWarmingRouting] = useState(PREPARED);
  const [calculating, setCalculating] = useState(false);
  const [mapMode, setMapMode] = useState<"idle" | "origin" | "report">("idle");
  const selecting = mapMode !== "idle";
  const reportPlacement = mapMode === "report";
  const [problem, setProblem] = useState<Problem | null>(null);
  const [status, setStatus] = useState("");
  const [panelExpanded, setPanelExpanded] = useState(true);
  const [showStops, setShowStops] = useState(false);
  const [mapCenter, setMapCenter] = useState<[number, number] | null>(null);
  const [evidenceFeatures, setEvidenceFeatures] = useState<GeoJSON.FeatureCollection<GeoJSON.Point>>({ type: "FeatureCollection", features: [] });
  const [sidewalkFeatures, setSidewalkFeatures] = useState<GeoJSON.FeatureCollection>({ type: "FeatureCollection", features: [] });
  const [reportPoint, setReportPoint] = useState<[number, number] | null>(null);
  const [reportFocus, setReportFocus] = useState(0);
  const [candidateFocus, setCandidateFocus] = useState<[number, number] | null>(null);
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);
  const [rankedStops, setRankedStops] = useState<GapDetail[]>([]);
  const [scheduleNotice, setScheduleNotice] = useState<ScheduleNotice | null>(null);
  const dataLoadRef = useRef<Promise<void> | null>(null);
  const requestRef = useRef<AbortController | null>(null);
  const compareRef = useRef<AbortController | null>(null);
  const viewTitleRef = useRef<HTMLHeadingElement>(null);
  const locationCenterAttempted = useRef(false);
  const methodsTitleRef = useRef<HTMLHeadingElement>(null);

  const destination = useMemo(() => (place ? nearestStop(place, origin) : null), [place, origin]);
  const countyOutlinePath = useMemo(() => coverageOutlinePath(coverage), [coverage]);

  useEffect(() => {
    try { localStorage.setItem("transitgap-profile-v1", profile); } catch { /* optional preference */ }
  }, [profile]);

  useEffect(() => {
    setScheduleNotice(null);
    if (!destination) return;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 5000);
    fetch(`${API}/stops/${encodeURIComponent(destination.stop_id)}`, { signal: controller.signal, cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) return null;
        return response.json();
      })
      .then((data) => {
        const service = data?.service;
        const validity = service?.schedule_validity;
        if (!service || !validity || validity.status === "current") return;
        const start = feedDate(validity.feed_start_date || service.feed_info?.[0]?.feed_start_date);
        const end = feedDate(validity.feed_end_date || service.feed_info?.[0]?.feed_end_date);
        setScheduleNotice({
          message: validity.status === "unknown"
            ? `The loaded ${data.agency} timetable doesn't state which dates it covers. Check the agency for today's times.`
            : `This timetable doesn't cover today. The loaded feed covers ${start} to ${end}. Check ${data.agency} for today's times.`,
          agency: data.agency,
          url: data.schedule_url || data.agency_url,
        });
      })
      .catch(() => { /* Schedule status is supplemental; route planning remains available. */ })
      .finally(() => window.clearTimeout(timeout));
    return () => { window.clearTimeout(timeout); controller.abort(); };
  }, [destination?.stop_id]);

  const startRouting = useCallback(async () => {
    setWarmingRouting(true);
    const ready = await warmRouting();
    setRoutingWarm((wasReady) => wasReady || ready);
    setWarmingRouting(false);
  }, []);

  const loadData = useCallback(() => {
    if (dataLoadRef.current) return dataLoadRef.current;
    setLoading(true);
    setProblem(null);
    const request = (async () => {
      try {
        if (PREPARED) void startRouting();
        const { coverage: nextCoverage, stops: loadedStops } = await plannerData();
        setCoverage(nextCoverage);
        setStops(loadedStops);
        const params = new URLSearchParams(location.search);
        const shared = params.get("stop");
        if (shared) {
          const sharedPlace = buildPlaces(loadedStops).find((p) => p.stops.some((s) => s.stop_id === shared));
          if (sharedPlace) setPlace(sharedPlace);
        }
        const lat = Number(params.get("lat")), lon = Number(params.get("lon"));
        if (params.has("lat") && params.has("lon") && Number.isFinite(lat) && Number.isFinite(lon) && insideCoverage([lat, lon], nextCoverage)) {
          setOrigin([lat, lon]);
          setOriginLabel("Shared starting point");
        }
        setDataReady(true);
        setStatus("Route planner ready");
      } catch {
        setDataReady(false);
        setProblem({ message: CONNECTION_PROBLEM, retry: () => void loadData() });
        setStatus("Map is available. Transit stops couldn't be loaded.");
      } finally {
        setLoading(false);
        dataLoadRef.current = null;
      }
    })();
    dataLoadRef.current = request;
    return request;
  }, [startRouting]);

  useEffect(() => {
    void loadData();
    return () => requestRef.current?.abort();
  }, [loadData]);

  useEffect(() => {
    if (!coverage || origin || locationCenterAttempted.current) return;
    locationCenterAttempted.current = true;
    if (!navigator.geolocation || !navigator.permissions) return;
    const permissions = navigator.permissions as Permissions & {
      query: (descriptor: { name: "geolocation" }) => Promise<PermissionStatus>;
    };
    void permissions.query({ name: "geolocation" }).then((permission) => {
      // Do not prompt on page load. Use a location only when the user has
      // already granted permission; otherwise keep the district overview.
      if (permission.state !== "granted") return;
      navigator.geolocation.getCurrentPosition(
        (position) => {
          const point: [number, number] = [position.coords.latitude, position.coords.longitude];
          if (insideCoverage(point, coverage)) setCandidateFocus(point);
        },
        () => undefined,
        { enableHighAccuracy: false, timeout: 6000, maximumAge: 120000 },
      );
    }).catch(() => undefined);
  }, [coverage, origin]);

  const currentKey = useMemo<RouteKey | null>(
    () => (origin && destination ? { origin, stopId: destination.stop_id, algorithm, profile } : null),
    [origin, destination, algorithm, profile],
  );
  const resultIsCurrent = Boolean(
    result && resultKey && currentKey &&
      resultKey.stopId === currentKey.stopId &&
      resultKey.algorithm === currentKey.algorithm &&
      resultKey.profile === currentKey.profile &&
      resultKey.origin[0] === currentKey.origin[0] &&
      resultKey.origin[1] === currentKey.origin[1],
  );
  const showingResult = view === "route" && !editing && Boolean(place) && Boolean(result) && (resultIsCurrent || recalculating);
  const routeActive = view === "route" && (resultIsCurrent || calculating);
  const mapDestination = useMemo(() => {
    const arrival = result?.arrival;
    if (!destination || !resultIsCurrent || arrival?.type !== "entrance" ||
        arrival.latitude == null || arrival.longitude == null) return destination;
    return {
      ...destination,
      latitude: arrival.latitude,
      longitude: arrival.longitude,
      stop_name: `${place?.name || destination.stop_name}, ${arrival.name || "station entrance"}`,
    };
  }, [destination, place, result, resultIsCurrent]);

  const missingReason = !dataReady
    ? loading ? "Loading transit stops…" : "Transit stops couldn't be loaded."
    : !origin && !place ? "Choose where you're starting and where you're going."
    : !origin ? "Choose where you're starting."
    : !place ? "Choose where you're going."
    : "";
  const canRoute = !missingReason && !calculating;
  const plannerStep = !origin ? "origin" : !place ? "destination" : "ready";
  const nextAction = !dataReady ? loading ? "Loading stops…" : "Retry loading stops" : !origin ? "Choose a starting point" : !place ? "Choose a destination" : "Find route";
  const previousInputs = useRef({ origin, place });

  const revealStep = useCallback((id: string) => {
    requestAnimationFrame(() => {
      const target = document.getElementById(id);
      const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      target?.focus({ preventScroll: true });
      target?.scrollIntoView({ block: "nearest", behavior: reduceMotion ? "instant" : "smooth" });
      if (!reduceMotion) target?.closest(".step-section")?.animate(
        [{ backgroundColor: "transparent" }, { backgroundColor: "#e9f2e8", offset: .35 }, { backgroundColor: "transparent" }],
        { duration: 1200 },
      );
    });
  }, []);

  useEffect(() => {
    const changed = previousInputs.current.origin !== origin || previousInputs.current.place !== place;
    previousInputs.current = { origin, place };
    if (!changed || (!origin && !place) || view !== "route" || showingResult || selecting) return;
    revealStep(!origin ? "origin-title" : !place ? "destination-title" : "travel-title");
  }, [origin, place, view, showingResult, selecting, revealStep]);

  useEffect(() => {
    if (!problem) return;
    setPanelExpanded(true);
    revealStep("planner-problem");
  }, [problem, revealStep]);

  const cancelRouteRequest = () => {
    requestRef.current?.abort();
    requestRef.current = null;
    setCalculating(false);
    setRecalculating(false);
  };

  const setStart = (point: [number, number], label: string) => {
    if (coverage && !insideCoverage(point, coverage)) {
      setProblem({ message: "That point is outside Santa Clara County. Choose a point inside the county boundary shown on the map." });
      setStatus("Starting point was not changed");
      setPanelExpanded(true);
      return;
    }
    cancelRouteRequest();
    setOrigin(point);
    setOriginLabel(label);
    setCandidateFocus(point);
    setMapMode("idle");
    setPanelExpanded(true);
    setProblem(null);
    setStatus(`Starting point set: ${label}`);
  };

  const cancelMapSelection = useCallback(() => {
    setMapMode("idle");
    setPanelExpanded(true);
    setStatus("Map selection cancelled");
  }, []);

  useEffect(() => {
    if (mapMode === "idle") return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") cancelMapSelection();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mapMode, cancelMapSelection]);

  const useMyLocation = () => {
    setProblem(null);
    if (!navigator.geolocation) {
      setProblem({ message: "Location isn't available in this browser. Search an address or choose on the map instead." });
      return;
    }
    setStatus("Finding your location…");
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLocating(false);
        setStart([position.coords.latitude, position.coords.longitude], "Your location");
      },
      (geoError) => {
        setLocating(false);
        setProblem({
          message:
            geoError.code === 1
              ? "Location access was denied. Search an address or choose on the map instead."
              : "Your location couldn't be found. Search an address or choose on the map instead.",
        });
      },
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 },
    );
  };

  const choosePlace = useCallback((next: Place) => {
    requestRef.current?.abort();
    setCalculating(false);
    setPlace(next);
    setMapMode("idle");
    setPanelExpanded(true);
    setProblem(null);
    setStatus(`Destination set: ${next.name}`);
  }, []);

  const chooseStop = useCallback(
    (stop: Stop) => {
      const match = places.find((p) => p.stops.some((s) => s.stop_id === stop.stop_id));
      if (match) choosePlace(match);
    },
    [places, choosePlace],
  );

  const calculate = async (overrides: { profile?: string } = {}) => {
    if (!origin || !place || !dataReady) return;
    const stop = nearestStop(place, origin);
    const routeProfile = overrides.profile ?? profile;
    const key: RouteKey = { origin, stopId: stop.stop_id, algorithm, profile: routeProfile };
    requestRef.current?.abort();
    const controller = new AbortController();
    const timeoutController = new AbortController();
    const startedAt = performance.now();
    let phase = "routing_warmup";
    const attemptTimeout = window.setTimeout(() => timeoutController.abort(), 12_000);
    const signal = AbortSignal.any([controller.signal, timeoutController.signal]);
    requestRef.current = controller;
    setCalculating(true);
    setComparison(null);
    setProblem(null);
    setStatus(`Finding a route for ${profileLabel(routeProfile)}…`);
    try {
      if (!routingWarm) {
        setStatus("Preparing the walking network. Your trip is queued; you can still change either location.");
        const ready = await waitForSignal(warmRouting(), signal);
        if (controller.signal.aborted) return;
        if (timeoutController.signal.aborted) throw Object.assign(new Error("Route preparation timed out."), { status: 408 });
        if (!ready) throw Object.assign(new Error("The routing service is still starting. Please try again."), { status: 503 });
        setRoutingWarm(true);
      }
      phase = "route_request";
      let response: Response;
      try {
        response = await fetch(`${API}/route`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            origin_latitude: origin[0],
            origin_longitude: origin[1],
            destination_stop_id: stop.stop_id,
            algorithm,
            profile: routeProfile,
          }),
          signal,
        });
      } catch (error) {
        if (controller.signal.aborted) return;
        if (timeoutController.signal.aborted) throw Object.assign(new Error("Route request timed out."), { status: 408 });
        throw Object.assign(new Error(String(error)), { status: 0 });
      }
      phase = "response_body";
      let data: unknown;
      try {
        data = await response.json();
      } catch (error) {
        if (controller.signal.aborted) return;
        if (timeoutController.signal.aborted) throw Object.assign(new Error("Route response timed out."), { status: 408 });
        throw Object.assign(new Error(String(error)), { status: 0 });
      }
      if (controller.signal.aborted) return;
      if (timeoutController.signal.aborted) throw Object.assign(new Error("Route response timed out."), { status: 408 });
      if (!response.ok) throw Object.assign(new Error(detailOf(data)), { status: response.status });
      setRoutingWarm(true);
      setResult(data as Route);
      setResultKey(key);
      setEditing(false);
      setPanelExpanded(true);
      const route = data as Route;
      setStatus(`Route found: ${formatDistance(route.distance_m)}, about ${formatDuration(route.duration_seconds)}, ${(route.directions || []).length} directions.`);
    } catch (error) {
      if (controller.signal.aborted) return;
      const status = timeoutController.signal.aborted ? 408 : (error as { status?: number }).status ?? 0;
      const failure = status === 408 ? "client_timeout" : status === 0 ? "connection_failure" : "route_failure";
      console.warn("TransitGap route attempt failed", {
        phase,
        elapsed_ms: Math.round(performance.now() - startedAt),
        failure,
        http_status: status || undefined,
      });
      setProblem({ message: routeProblem(status, (error as Error).message), retry: () => void calculate(overrides) });
      setStatus("The route couldn't be calculated");
    } finally {
      window.clearTimeout(attemptTimeout);
      if (requestRef.current === controller) {
        requestRef.current = null;
        setCalculating(false);
        setRecalculating(false);
      }
    }
  };

  const changeProfile = (next: string) => {
    setProfile(next);
    // A shown route always matches the selected profile: recalculate at once.
    if (showingResult) {
      setRecalculating(true);
      void calculate({ profile: next });
    }
  };

  const newTrip = () => {
    cancelRouteRequest();
    setOrigin(null);
    setOriginLabel("");
    setPlace(null);
    setResult(null);
    setResultKey(null);
    setComparison(null);
    setEditing(false);
    setMapMode("idle");
    setProblem(null);
    setBenchmark([]);
    history.replaceState(null, "", location.pathname);
    setStatus("Plan a new trip");
    setPanelExpanded(true);
    requestAnimationFrame(() => document.getElementById("origin-title")?.focus());
  };

  const clearTrip = () => {
    newTrip();
    setProfile("standard");
    try { localStorage.setItem("transitgap-profile-v1", "standard"); } catch { /* optional preference */ }
    setStatus("Trip cleared. Choose a starting point to begin again.");
  };

  const goTo = (next: View) => {
    setView(next);
    setPanelExpanded(true);
    if (next === "advocates") setCandidateFocus(null);
    setProblem(null);
    if (next === "report") setReportFocus((n) => n + 1);
    if (next === "route") {
      setEvidenceFeatures({ type: "FeatureCollection", features: [] });
      setSidewalkFeatures({ type: "FeatureCollection", features: [] });
    }
    requestAnimationFrame(() =>
      (next === "route"
        ? document.getElementById(showingResult ? "route-title" : "origin-title")
        : next === "report" ? document.getElementById("report-title")
        : next === "methods" ? methodsTitleRef.current : viewTitleRef.current
      )?.focus(),
    );
  };

  const routeFeature = useMemo(
    () => (result && resultIsCurrent ? { type: "Feature" as const, properties: {}, geometry: result.geometry } : null),
    [result, resultIsCurrent],
  );
  const routeSegments = useMemo<GeoJSON.FeatureCollection>(
    () => ({
      type: "FeatureCollection",
      features:
        result && resultIsCurrent && view === "route"
          ? (result.segments || []).map((segment, index, all) => {
              const concerns = (item: { reasons: string[] }) =>
                // Same rule as the "Mapped concerns" list: crossings are
                // described in text, not marked as concerns.
                item.reasons.filter((r) => !r.startsWith("Missing ") && !r.startsWith("Off-network") && r !== "Mapped unmarked crossing").join("|");
              // One marker per run of edges with the same documented concern
              // (one crossing is often split into several OSM edges).
              const key = concerns(segment);
              return {
                type: "Feature",
                properties: {
                  status: segment.status,
                  kind: /connector/i.test(segment.source || "") ? "connector" : segment.kind || "path",
                  concern: Boolean(key) && (index === 0 || concerns(all[index - 1]) !== key),
                },
                geometry: segment.geometry,
              };
            })
          : [],
    }),
    [result, resultIsCurrent, view],
  );
  const comparisonGeometry = useMemo<GeoJSON.FeatureCollection>(
    () => ({
      type: "FeatureCollection",
      features:
        comparison && resultIsCurrent && view === "route" && comparison.alternative && !comparison.same_mapped_route
          ? [{ type: "Feature", properties: {}, geometry: comparison.standard.geometry }]
          : [],
    }),
    [comparison, resultIsCurrent, view],
  );
  const studyGeometry = useMemo<GeoJSON.FeatureCollection>(
    () => ({
      type: "FeatureCollection",
      features:
        view === "advocates" && reachabilityStudy
          ? [
              ...(reachabilityLayers.documented ? reachabilityStudy.documented.geometry.features.map((feature) => ({ ...feature, properties: { ...feature.properties, profile: "documented" } })) : []),
              ...(reachabilityLayers.unknown ? reachabilityStudy.unknown_gap.geometry.features.map((feature) => ({ ...feature, properties: { ...feature.properties, profile: "unknown" } })) : []),
            ]
          : study && view === "advocates"
            ? [
                { type: "Feature", properties: { profile: "standard" }, geometry: study.standard.geometry },
                { type: "Feature", properties: { profile: "wheelchair" }, geometry: study.wheelchair.geometry },
              ]
            : [],
    }),
    [study, reachabilityStudy, reachabilityLayers, view],
  );
  const studyFocus = useMemo<[number, number] | null>(
    () =>
      reachabilityStudy && view === "advocates"
        ? [reachabilityStudy.stop.latitude, reachabilityStudy.stop.longitude]
        : study && view === "advocates"
          ? [study.latitude, study.longitude]
          : candidateFocus,
    [study, reachabilityStudy, view, candidateFocus],
  );
  const updateReachability = useCallback((analysis: ReachabilityAnalysis | null, layers: { documented: boolean; unknown: boolean }) => {
    setStudy(null);
    setReachabilityStudy(analysis);
    setReachabilityLayers(layers);
  }, []);
  useEffect(() => {
    setComparison(null);
    setBenchmark([]);
    compareRef.current?.abort();
    setComparing(false);
  }, [origin, place, profile]);
  const showEvidence = useCallback((gaps: GeoJSON.FeatureCollection<GeoJSON.Point>, sidewalks: GeoJSON.FeatureCollection) => {
    setEvidenceFeatures(gaps);
    setSidewalkFeatures(sidewalks);
  }, []);

  const advocateStopFeatures = useMemo<GeoJSON.FeatureCollection<GeoJSON.Point>>(() => ({
    type: "FeatureCollection",
    features: rankedStops.map((stop, index) => ({
      type: "Feature",
      properties: { rank: index + 1, stop_id: stop.stop_id, stop_name: stop.stop_name },
      geometry: { type: "Point", coordinates: [stop.longitude, stop.latitude] },
    })),
  }), [rankedStops]);

  async function compare() {
    if (!origin || !destination) return;
    const controller = new AbortController();
    compareRef.current = controller;
    setComparing(true);
    try {
      const response = await fetch(`${API}/compare`, {
        signal: controller.signal,
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ origin_latitude: origin[0], origin_longitude: origin[1], destination_stop_id: destination.stop_id, profile }),
      });
      const data = await response.json();
      if (!response.ok) throw Object.assign(new Error(detailOf(data)), { status: response.status });
      if (!controller.signal.aborted) setComparison(data);
    } catch (error) {
      if (!controller.signal.aborted)
        setProblem({ message: routeProblem((error as { status?: number }).status ?? 0, (error as Error).message), retry: () => void compare() });
    } finally {
      if (compareRef.current === controller) setComparing(false);
    }
  }

  async function runBenchmark() {
    if (!origin || !destination) return;
    setBenchmarking(true);
    try {
      const r = await fetch(`${API}/algorithms/compare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ origin_latitude: origin[0], origin_longitude: origin[1], destination_stop_id: destination.stop_id, profile }),
      });
      const data = await r.json();
      if (!r.ok) throw Object.assign(new Error(detailOf(data)), { status: r.status });
      setBenchmark(data.results);
    } catch (error) {
      setProblem({ message: routeProblem((error as { status?: number }).status ?? 0, (error as Error).message) });
    } finally {
      setBenchmarking(false);
    }
  }

  function share() {
    if (!origin || !destination) return;
    const url = new URL("/app", location.origin);
    url.search = new URLSearchParams({ lat: String(origin[0]), lon: String(origin[1]), stop: destination.stop_id, profile }).toString();
    history.replaceState(null, "", url);
    void navigator.clipboard
      ?.writeText(url.href)
      .then(() => setStatus("Trip link copied"))
      .catch(() => setStatus("The trip link is in the address bar"));
  }

  const handleMapOrigin = useCallback(
    (point: [number, number]) => {
      if (reportPlacement) {
        setReportPoint(point);
        setMapMode("idle");
        setPanelExpanded(true);
        setStatus("Report location chosen");
        return;
      }
      setStart(point, "Point chosen on the map");
    },
    // setStart reads coverage, the only state it depends on.
    [reportPlacement, coverage],
  );

  const reference: [number, number] | null =
    origin || mapCenter || (coverage ? [coverage.center.latitude, coverage.center.longitude] : null);

  const sheetSummary = showingResult && result && place
    ? `To ${place.duplicateName ? `${place.name} — ${place.disambiguation.split(" · ")[0]}` : place.name}: ${formatDistance(result.distance_m)}, ${formatDuration(result.duration_seconds)}`
    : view === "route" ? nextAction : view === "report" ? "Report an issue" : view === "methods" ? "Data & limits" : "For cities and advocates";

  return (
    <main
      className={`app-shell ${panelExpanded ? "" : "sheet-is-collapsed"} ${routeActive ? "route-active" : ""}`}
      data-data-state={dataReady ? "ready" : loading ? "loading" : "error"}
    >
      <a href="#origin-title" className="app-skip" onClick={(event) => { event.preventDefault(); goTo("route"); }}>
        Skip to route planner
      </a>
      <section className="map-shell" aria-label="Map">
        <Suspense fallback={<div className="map" role="status">Loading the map. The route planner is available.</div>}>
        <MapView
          coverage={coverage}
          stops={stops}
          origin={origin}
          destination={mapDestination}
          route={view === "route" ? routeFeature : null}
          segments={routeSegments}
          comparison={comparisonGeometry}
          study={studyGeometry}
          selecting={selecting}
          panelExpanded={panelExpanded}
          onReady={() => setMapReady(true)}
          onOrigin={handleMapOrigin}
          onStop={chooseStop}
          evidence={evidenceFeatures}
          sidewalks={sidewalkFeatures}
          advocateStops={advocateStopFeatures}
          showAdvocateStops={view === "advocates"}
          focusPoint={studyFocus}
          onCandidate={(id) => {
            setSelectedCandidateId(id);
            goTo("advocates");
          }}
          reportPoint={reportPoint}
          routeActive={routeActive}
          showStops={showStops}
          onViewChange={setMapCenter}
        />
        </Suspense>
        {coverage?.boundary && (
          <div className="map-coverage-badge" role="img" aria-label="Outline of Santa Clara County route coverage">
            <svg viewBox="0 0 56 36" aria-hidden="true" focusable="false">
              <path d={countyOutlinePath} />
            </svg>
            <span>Santa Clara County route coverage</span>
          </div>
        )}
        <div className="map-tools">
          {routeActive && (
            <button type="button" className="map-tool" aria-pressed={showStops} onClick={() => setShowStops((value) => !value)}>
              {showStops ? "Hide other stops" : "Show other stops"}
            </button>
          )}
          <details className="map-legend">
            <summary>Map key</summary>
            <span><b className="key-marker">A</b> Your start</span>
            <span><b className="key-marker key-b">B</b> Your destination</span>
            {coverage?.boundary && <span className="legend-coverage"><i className="legend-coverage-line" aria-hidden="true" /> Santa Clara County route coverage boundary</span>}
            {coverage?.boundary && <span className="legend-pilot"><i className="legend-pilot-line" aria-hidden="true" /> Diridon pilot: detailed City sidewalk records</span>}
            {routeActive ? (
              <>
                <span className="legend-route">Walking route</span>
                <span className="legend-connector">No walking-path data here</span>
                <span><b className="key-dot" /> Possible issue recorded in map data</span>
                {comparisonGeometry.features.length > 0 && <span className="legend-standard">Standard walking route</span>}
              </>
            ) : (
              <span><b className="key-stop" /> Transit stop or station. Numbers show how many stops are grouped.</span>
            )}
            {view === "advocates" && <span><b className="key-rank">1</b> Highest wheelchair-model gap in the sample</span>}
          </details>
        </div>
        {selecting && (
          <div className="map-selection-banner" role="status">
            <span>{reportPlacement ? "Tap the map where the problem is" : "Tap the map where you're starting"}</span>
            <button type="button" onClick={cancelMapSelection}>
              Cancel<span className="sr-only"> choosing on the map</span>
            </button>
          </div>
        )}
      </section>
      <aside className={`panel ${panelExpanded ? "panel-expanded" : "panel-collapsed"}`} aria-label="Route planner">
        <div className="panel-scroll">
          <header className="panel-header">
            <a className="brand-lockup" href="/" aria-label="TransitGap home">
              <h1>TransitGap</h1>
            </a>
            <button type="button" className="sheet-summary" aria-hidden={panelExpanded} tabIndex={panelExpanded ? -1 : 0}
              onClick={() => { setPanelExpanded(true); if (view === "route" && !showingResult) revealStep(!origin ? "origin-title" : !place ? "destination-title" : "travel-title"); }}>
              {sheetSummary}
            </button>
            {view !== "report" && (
              <button className="text-button report-shortcut" type="button" onClick={() => goTo("report")}>
                Report an issue
              </button>
            )}
            <button
              className="mobile-panel-toggle icon-button"
              type="button"
              onClick={() => setPanelExpanded(!panelExpanded)}
              aria-label={panelExpanded ? "Show more map" : "Show the planner"}
              aria-expanded={panelExpanded}
            >
              {panelExpanded ? <ChevronDown size={22} /> : <ChevronUp size={22} />}
            </button>
          </header>
          <div className="panel-content">
            {view !== "route" && (
              <button type="button" className="back-link" onClick={() => goTo("route")}>
                ← Back to route planning
              </button>
            )}
            {problem && (
              <div className="notice error" role="alert" id="planner-problem" tabIndex={-1}>
                <p>{problem.message}</p>
                {problem.retry && (
                  <button className="button" type="button" onClick={problem.retry}>
                    Try again
                  </button>
                )}
              </div>
            )}
            {view === "route" && showingResult && result && place && (
              <RouteResult
                route={result}
                place={place}
                profile={profile}
                updating={calculating || !resultIsCurrent}
                onProfile={changeProfile}
                onEdit={() => {
                  setEditing(true);
                  requestAnimationFrame(() => document.getElementById("origin-title")?.focus());
                }}
                onNewTrip={newTrip}
                onClearTrip={clearTrip}
                onShare={share}
                onFocusStep={(point) => setCandidateFocus([...point] as [number, number])}
                comparison={comparison}
                comparing={comparing}
                onCompare={() => void compare()}
              />
            )}
            {view === "route" && !showingResult && (
              <div className="planner" role="group" aria-label="Plan a route" data-next-step={plannerStep}>
                <p className="coverage-summary">TransitGap covers Santa Clara County. Detailed city sidewalk records cover the Diridon pilot only.</p>
                <section className={`step-section ${plannerStep === "origin" ? "step-current" : "step-complete"}`} aria-labelledby="origin-title">
                  <h2 id="origin-title" tabIndex={-1}><span className="step-number" aria-hidden="true">{origin ? "✓" : "1"}</span>Where are you starting?</h2>
                  {origin ? (
                    <div className="field-value">
                      <span className="field-value-text">
                        <strong>{originLabel || "Starting point"}</strong>
                        <span className="sr-only">{origin[0].toFixed(5)}, {origin[1].toFixed(5)}</span>
                      </span>
                      <button type="button" className="text-button field-change" onClick={() => { cancelRouteRequest(); setProblem(null); setOrigin(null); setOriginLabel(""); setResult(null); setResultKey(null); }}>
                        Change<span className="sr-only"> starting point</span>
                      </button>
                    </div>
                  ) : (
                    <>
                      <div className="origin-actions">
                        <button type="button" className="button location-action" onClick={useMyLocation} disabled={locating} aria-busy={locating}>
                          {locating ? <><span className="spinner" aria-hidden="true" /> Finding location…</> : "Use my location"}
                        </button>
                        <button
                          type="button"
                          className="button"
                          aria-pressed={mapMode === "origin"}
                          onClick={() => {
                            if (mapMode === "origin") return cancelMapSelection();
                            setMapMode("origin");
                            setPanelExpanded(false);
                            setProblem(null);
                            setStatus("Tap the map where you're starting. Press Escape to cancel.");
                          }}
                        >
                          Choose on map
                        </button>
                      </div>
                      <OriginSearch onChoose={setStart} onInputChange={() => setProblem(null)} />
                    </>
                  )}
                </section>
                <section className={`step-section ${plannerStep === "destination" ? "step-current" : place ? "step-complete" : ""}`} aria-labelledby="destination-title">
                  <h2 id="destination-title" tabIndex={-1}><span className="step-number" aria-hidden="true">{place ? "✓" : "2"}</span><label htmlFor="stop-search">Where are you going?</label></h2>
                  <StopSearch
                    places={places}
                    selected={place}
                    reference={reference}
                    referenceLabel={origin ? "your starting point" : "the middle of the map"}
                    disabled={!dataReady}
                    onSelect={choosePlace}
                    onClear={() => { cancelRouteRequest(); setProblem(null); setPlace(null); setResult(null); setResultKey(null); }}
                    onInputChange={() => setProblem(null)}
                  />
                </section>
                {scheduleNotice && destination && (
                  <p className="notice schedule-notice" role="status">
                    {scheduleNotice.message}{" "}
                    <a href={scheduleNotice.url} target="_blank" rel="noreferrer">Check {scheduleNotice.agency}</a>.
                  </p>
                )}
                <fieldset className={`step-section profile-section ${plannerStep === "ready" ? "step-current" : ""}`}>
                  <legend><h2 id="travel-title" tabIndex={-1}><span className="step-number" aria-hidden="true">3</span>How do you travel?</h2></legend>
                  <div className="profile-options">
                    {PROFILES.map((option) => (
                      <label key={option.value}>
                        <input type="radio" name="profile" value={option.value} checked={profile === option.value} onChange={() => { setProblem(null); setProfile(option.value); }} />
                        <span>{option.label}</span>
                      </label>
                    ))}
                  </div>
                  <p className="profile-persistence-note">Your travel profile stays selected for new trips. “Clear trip / Start over” resets it to Walking.</p>
                </fieldset>
                {PREPARED && dataReady && !routingWarm && !warmingRouting && (
                  <button className="text-button" type="button" onClick={() => void startRouting()}>Try connecting again</button>
                )}
                {editing && resultIsCurrent && (
                  <button type="button" className="text-button" onClick={() => setEditing(false)}>Back to the current route</button>
                )}
                {dataReady && (
                  <div className="example-trips" aria-label="Example trips">
                  <button
                    type="button"
                    className="text-button example-link"
                    onClick={() => {
                      const example = places.find((p) => p.stops.some((s) => s.stop_name === "San Jose Diridon (Bay 11)"));
                      if (example) {
                        setStart([37.32875, -121.90442], "Example: near Diridon Station");
                        choosePlace(example);
                      }
                    }}
                  >
                    Try an example trip near Diridon Station
                  </button>
                  <button
                    type="button"
                    className="text-button example-link"
                    onClick={() => {
                      const example = places.find((p) => p.stops.some((s) => s.stop_id === "bart:S40-1"));
                      if (example) {
                        setStart([37.4076, -121.8910], "Example: near Milpitas BART");
                        choosePlace(example);
                      }
                    }}
                  >
                    Try an example trip to Milpitas BART
                  </button>
                  </div>
                )}
                <details className="quiet-details advanced-settings">
                  <summary>Advanced options</summary>
                  <label className="inline-check">
                    <input type="radio" name="profile" value="prefer_documented_paths" checked={profile === "prefer_documented_paths"} onChange={() => setProfile("prefer_documented_paths")} />
                    Prefer paths with documented accessibility information
                  </label>
                  <label htmlFor="algorithm">Routing algorithm</label>
                    <select id="algorithm" value={algorithm} onChange={(e) => { setProblem(null); setAlgorithm(e.target.value); }}>
                    {algorithms.map((item) => (
                      <option value={item.value} key={item.value}>{item.label}</option>
                    ))}
                  </select>
                  <p>{algorithms.find((a) => a.value === algorithm)?.description}</p>
                  <button type="button" className="button" onClick={() => void runBenchmark()} disabled={!origin || !destination || benchmarking}>
                    {benchmarking ? "Measuring…" : "Compare all five algorithms"}
                  </button>
                  {benchmark.length > 0 && !benchmark.some((row) => !row.error) && (
                    <p role="status" className="benchmark-unavailable">No tested algorithm found a route. Move the start to a nearby street entrance or choose another stop.</p>
                  )}
                  {benchmark.length > 0 && benchmark.some((row) => !row.error) && (
                    <>
                      <table className="benchmark-table">
                        <thead><tr><th>Algorithm</th><th>ms</th><th>Distance</th></tr></thead>
                        <tbody>
                          {benchmark.map((row) => (
                            <tr key={row.algorithm}>
                              <th>{algorithms.find((a) => a.value === row.algorithm)?.label}</th>
                              <td>{row.computation_time_ms?.toFixed(1) || row.error}</td>
                              <td>{row.distance_m != null ? formatDistance(row.distance_m) : "Unavailable"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      <p>Measured per request, including route reconstruction. Breadth-first search minimizes segments, not distance.</p>
                    </>
                  )}
                </details>
                {(origin || place) && <button type="button" className="text-button clear-trip" onClick={clearTrip}>Clear trip / Start over</button>}
              </div>
            )}
            {view === "route" && (
              <nav className="explore-links" aria-label="Accessibility information">
                <button type="button" className="button advocate-link" onClick={() => goTo("advocates")}>For cities and advocates</button>
              </nav>
            )}
            {view === "advocates" && (
              <Suspense fallback={<p role="status">Loading accessibility gaps…</p>}>
                <section className="advocate-overview" aria-labelledby="advocates-title">
                  <h2 id="advocates-title" ref={viewTitleRef} tabIndex={-1}>For cities and advocates</h2>
                  <p>Nearby records are prompts for a closer look, not confirmed barriers. The wheelchair ranking below is a 32-stop sample, not a countywide ranking.</p>
                </section>
                <GapPanel places={places} onStudy={setStudy} onReachability={updateReachability} onRanking={setRankedStops} />
                <GroundTruthPanel
                  mode="evidence"
                  stops={stops}
                  onFeatures={showEvidence}
                  onClearReportPoint={() => setReportPoint(null)}
                  onRequestLocation={() => {
                    setMapMode("report");
                    setPanelExpanded(false);
                    setStatus("Tap the map where the problem is. Press Escape to cancel.");
                  }}
                  reportPoint={reportPoint}
                  onFocusCandidate={(point) => { setCandidateFocus(point); setSelectedCandidateId(null); }}
                  selectedCandidateId={selectedCandidateId}
                  onReport={() => goTo("report")}
                />
              </Suspense>
            )}
            {view === "methods" && (
              <section className="methods-panel" aria-labelledby="methods-title">
                <h2 id="methods-title" ref={methodsTitleRef} tabIndex={-1}>Data & limits</h2>
                <p>TransitGap uses public map and transit records to suggest walking routes. The routes have not been checked in person, and missing information does not mean a sidewalk or crossing is safe or unsafe.</p>
                <ul>
                  <li>Walking routes cover Santa Clara County. Detailed city sidewalk records are available only in the Diridon pilot area.</li>
                  <li>The wheelchair comparison covers a small sample of stops, not every stop in the county.</li>
                  <li>Some connections have no walking-path data, so TransitGap cannot confirm a usable path there.</li>
                </ul>
                <details className="plain-details">
                  <summary>More detail</summary>
                  <ul>
                    <li>Each route search has a 3-second network-search limit. A starting point can snap up to 120 m to a mapped walking path.</li>
                    <li>Estimated speeds are 2.7 mph for walking and low vision, and 2.0 mph for wheelchair and stroller profiles.</li>
                    <li>The wheelchair stop ranking uses a reproducible 32-stop sample. It is not a countywide ranking of the hardest stops.</li>
                    <li>Connections without a walking-path record use straight-line estimates and have not been checked for a usable path.</li>
                  </ul>
                  <a href="https://github.com/TaxCollector23/transitgap/blob/main/docs/CAC_METHODS.md" target="_blank" rel="noreferrer">Full technical methodology</a>
                </details>
              </section>
            )}
            {view === "report" && (
              <Suspense fallback={<p role="status">Loading…</p>}>
                <GroundTruthPanel
                  key={view}
                  mode="report"
                  stops={stops}
                  onReport={() => goTo("report")}
                  onFeatures={showEvidence}
                  onClearReportPoint={() => setReportPoint(null)}
                  onRequestLocation={() => {
                    setMapMode("report");
                    setPanelExpanded(false);
                    setStatus("Tap the map where the problem is. Press Escape to cancel.");
                  }}
                  reportPoint={reportPoint}
                  onFocusCandidate={(point) => {
                    setCandidateFocus(point);
                    setSelectedCandidateId(null);
                  }}
                  selectedCandidateId={selectedCandidateId}
                  focusReport={reportFocus}
                />
              </Suspense>
            )}
            {!mapReady && <p className="field-hint" role="status">The map is loading. You can use these controls in the meantime.</p>}
            <footer className="panel-footer">
              <p>Directions come from OpenStreetMap and agency timetables. They aren't checked in person and aren't live.</p>
              <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>
              <a href="https://www.vta.org/go/developers">VTA</a>
              <a href="https://www.caltrain.com/developer-resources">Caltrain</a>
              <a href="https://www.bart.gov/schedules/developers/gtfs">BART</a>
              <button type="button" className="text-button" onClick={() => goTo("methods")}>Data & limits</button>
            </footer>
          </div>
        </div>
        {view === "route" && !showingResult && !selecting && (
          <div className={`planner-action ${canRoute ? "planner-action-ready" : ""}`}>
            <button className="button button-primary find-route" type="button"
              onClick={() => {
                if (!dataReady) void loadData();
                else if (canRoute) void calculate();
                else revealStep(!origin ? "origin-title" : "destination-title");
              }}
              disabled={(!dataReady && loading) || calculating} aria-describedby={missingReason ? "route-missing" : undefined} aria-busy={calculating}>
              {calculating ? <><span className="spinner light" aria-hidden="true" /> {routingWarm ? "Finding route…" : "Preparing walking network…"}</> : <>{nextAction}<ArrowRight size={18} aria-hidden="true" /></>}
            </button>
            {missingReason && <span className="sr-only" id="route-missing">{missingReason}</span>}
          </div>
        )}
      </aside>
      <div className="sr-only" role="status" aria-live="polite">{status}</div>
    </main>
  );
}
