import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
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
type View = "route" | "gaps" | "evidence" | "report";
type RouteKey = { origin: [number, number]; stopId: string; algorithm: string; profile: string };
type Problem = { message: string; retry?: () => void };

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
  if (status === 503 || status >= 500 || status === 0) return CONNECTION_PROBLEM;
  if (/outside the supported area/i.test(detail)) return "That starting point is outside the area TransitGap covers. Choose a point inside the dotted boundary.";
  if (/time limit/i.test(detail)) return "This route took too long to calculate. Try again, or choose a closer stop.";
  if (/from the walk network|within .* of a mapped path/i.test(detail)) return "That starting point is too far from any mapped path. Choose a point on or near a street or path.";
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

export default function App() {
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [stops, setStops] = useState<Stop[]>([]);
  const places = useMemo(() => buildPlaces(stops), [stops]);
  const [origin, setOrigin] = useState<[number, number] | null>(null);
  const [originLabel, setOriginLabel] = useState("");
  const [place, setPlace] = useState<Place | null>(null);
  const [algorithm, setAlgorithm] = useState("astar");
  const [profile, setProfile] = useState("standard");
  const [view, setView] = useState<View>(
    new URLSearchParams(location.search).get("view") === "gaps" ? "gaps" : "route",
  );
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
  const dataLoadRef = useRef<Promise<void> | null>(null);
  const requestRef = useRef<AbortController | null>(null);
  const compareRef = useRef<AbortController | null>(null);
  const viewTitleRef = useRef<HTMLHeadingElement>(null);

  const destination = useMemo(() => (place ? nearestStop(place, origin) : null), [place, origin]);

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
        if (["standard", "wheelchair", "stroller", "low_vision", "prefer_documented_paths"].includes(params.get("profile") || ""))
          setProfile(params.get("profile")!);
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

  const cancelRouteRequest = () => {
    requestRef.current?.abort();
    requestRef.current = null;
    setCalculating(false);
    setRecalculating(false);
  };

  const setStart = (point: [number, number], label: string) => {
    if (coverage && !insideCoverage(point, coverage)) {
      setProblem({ message: "That point is outside the area TransitGap covers. Choose a point inside the dotted boundary." });
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
    navigator.geolocation.getCurrentPosition(
      (position) => setStart([position.coords.latitude, position.coords.longitude], "Your location"),
      (geoError) =>
        setProblem({
          message:
            geoError.code === 1
              ? "Location access was denied. Search an address or choose on the map instead."
              : "Your location couldn't be found. Search an address or choose on the map instead.",
        }),
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
    requestRef.current = controller;
    setCalculating(true);
    setComparison(null);
    setProblem(null);
    setStatus(`Finding a route for ${profileLabel(routeProfile)}…`);
    try {
      if (!routingWarm) {
        setStatus("Preparing the walking network. Your trip is queued; you can still change either location.");
        const ready = await warmRouting();
        if (controller.signal.aborted) return;
        if (!ready) throw Object.assign(new Error("The routing service is still starting. Please try again."), { status: 503 });
        setRoutingWarm(true);
      }
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
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(25000)]),
        });
      } catch (error) {
        if (controller.signal.aborted) return;
        throw Object.assign(new Error(String(error)), { status: 0 });
      }
      const data = await response.json().catch(() => ({}));
      if (controller.signal.aborted) return;
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
      const status = (error as { status?: number }).status ?? 0;
      setProblem({ message: routeProblem(status, (error as Error).message), retry: () => void calculate(overrides) });
      setStatus("The route couldn't be calculated");
    } finally {
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
    setStatus("Plan a new trip");
    setPanelExpanded(true);
    requestAnimationFrame(() => document.getElementById("origin-title")?.focus());
  };

  const goTo = (next: View) => {
    setView(next);
    setPanelExpanded(true);
    if (next === "report") setReportFocus((n) => n + 1);
    if (next === "route") {
      setEvidenceFeatures({ type: "FeatureCollection", features: [] });
      setSidewalkFeatures({ type: "FeatureCollection", features: [] });
    }
    requestAnimationFrame(() =>
      (next === "route"
        ? document.getElementById(showingResult ? "route-title" : "origin-title")
        : next === "report" ? document.getElementById("report-title") : viewTitleRef.current
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
        view === "gaps" && reachabilityStudy
          ? [
              ...(reachabilityLayers.documented ? reachabilityStudy.documented.geometry.features.map((feature) => ({ ...feature, properties: { ...feature.properties, profile: "documented" } })) : []),
              ...(reachabilityLayers.unknown ? reachabilityStudy.unknown_gap.geometry.features.map((feature) => ({ ...feature, properties: { ...feature.properties, profile: "unknown" } })) : []),
            ]
          : study && view === "gaps"
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
      reachabilityStudy && view === "gaps"
        ? [reachabilityStudy.stop.latitude, reachabilityStudy.stop.longitude]
        : study && view === "gaps"
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

  const sheetSummary = showingResult && result
    ? `To ${place?.name}: ${formatDistance(result.distance_m)}, ${formatDuration(result.duration_seconds)}`
    : view === "route" ? "Plan a route" : view === "report" ? "Report an issue" : "Accessibility gaps";

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
          focusPoint={studyFocus}
          onCandidate={(id) => {
            setSelectedCandidateId(id);
            goTo("evidence");
          }}
          reportPoint={reportPoint}
          routeActive={routeActive}
          showStops={showStops}
          onViewChange={setMapCenter}
        />
        </Suspense>
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
            {routeActive ? (
              <>
                <span className="legend-route">Walking route</span>
                <span className="legend-connector">Connection not on the map</span>
                <span><b className="key-dot" /> Mapped concern</span>
                {comparisonGeometry.features.length > 0 && <span className="legend-standard">Standard walking route</span>}
              </>
            ) : (
              <span><b className="key-stop" /> Transit stop or station. Numbers show how many stops are grouped.</span>
            )}
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
            <span className="sheet-summary" aria-hidden={panelExpanded}>{sheetSummary}</span>
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
              <div className="notice error" role="alert">
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
                onShare={share}
                onFocusStep={(point) => setCandidateFocus([...point] as [number, number])}
                comparison={comparison}
                comparing={comparing}
                onCompare={() => void compare()}
              />
            )}
            {view === "route" && !showingResult && (
              <div className="planner" role="group" aria-label="Plan a route">
                <section className="step-section" aria-labelledby="origin-title">
                  <h2 id="origin-title" tabIndex={-1}>Where are you starting?</h2>
                  {origin ? (
                    <div className="field-value">
                      <span className="field-value-text">
                        <strong>{originLabel || "Starting point"}</strong>
                        <span>{origin[0].toFixed(5)}, {origin[1].toFixed(5)}</span>
                      </span>
                      <button type="button" className="text-button field-change" onClick={() => { cancelRouteRequest(); setOrigin(null); setOriginLabel(""); }}>
                        Change<span className="sr-only"> starting point</span>
                      </button>
                    </div>
                  ) : (
                    <>
                      <div className="origin-actions">
                        <button type="button" className="button" onClick={useMyLocation}>Use my location</button>
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
                      <OriginSearch onChoose={setStart} />
                    </>
                  )}
                </section>
                <section className="step-section" aria-labelledby="destination-title">
                  <h2 id="destination-title"><label htmlFor="stop-search">Where are you going?</label></h2>
                  <StopSearch
                    places={places}
                    selected={place}
                    reference={reference}
                    referenceLabel={origin ? "your starting point" : "the middle of the map"}
                    disabled={!dataReady}
                    onSelect={choosePlace}
                    onClear={() => { cancelRouteRequest(); setPlace(null); }}
                  />
                </section>
                <fieldset className="step-section profile-section">
                  <legend><h2>How do you travel?</h2></legend>
                  <div className="profile-options">
                    {PROFILES.map((option) => (
                      <label key={option.value}>
                        <input type="radio" name="profile" value={option.value} checked={profile === option.value} onChange={() => setProfile(option.value)} />
                        <span>{option.label}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
                <button className="button button-primary find-route" type="button" onClick={() => void calculate()} disabled={!canRoute} aria-describedby={missingReason ? "route-missing" : undefined} aria-busy={calculating}>
                  {calculating ? <><span className="spinner light" aria-hidden="true" /> {routingWarm ? "Finding route…" : "Preparing walking network…"}</> : "Find route"}
                </button>
                {missingReason && <p className="field-hint" id="route-missing">{missingReason}</p>}
                {PREPARED && dataReady && !routingWarm && !warmingRouting && (
                  <button className="text-button" type="button" onClick={() => void startRouting()}>Try connecting again</button>
                )}
                {editing && resultIsCurrent && (
                  <button type="button" className="text-button" onClick={() => setEditing(false)}>Back to the current route</button>
                )}
                {!origin && !place && dataReady && (
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
                )}
                <details className="quiet-details advanced-settings">
                  <summary>Advanced options</summary>
                  <label className="inline-check">
                    <input type="radio" name="profile" value="prefer_documented_paths" checked={profile === "prefer_documented_paths"} onChange={() => setProfile("prefer_documented_paths")} />
                    Prefer paths with documented accessibility information
                  </label>
                  <label htmlFor="algorithm">Routing algorithm</label>
                  <select id="algorithm" value={algorithm} onChange={(e) => setAlgorithm(e.target.value)}>
                    {algorithms.map((item) => (
                      <option value={item.value} key={item.value}>{item.label}</option>
                    ))}
                  </select>
                  <p>{algorithms.find((a) => a.value === algorithm)?.description}</p>
                  <button type="button" className="button" onClick={() => void runBenchmark()} disabled={!origin || !destination || benchmarking}>
                    {benchmarking ? "Measuring…" : "Compare all five algorithms"}
                  </button>
                  {benchmark.length > 0 && (
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
              </div>
            )}
            {view === "route" && (
              <nav className="explore-links" aria-label="Accessibility information">
                <button type="button" className="text-button" onClick={() => goTo("gaps")}>Which stops are harder to reach by wheelchair?</button>
                <button type="button" className="text-button" onClick={() => goTo("evidence")}>Sidewalk records that need review</button>
              </nav>
            )}
            {view === "gaps" && (
              <Suspense fallback={<p role="status">Loading accessibility gaps…</p>}>
                <h2 className="sr-only" ref={viewTitleRef} tabIndex={-1}>Accessibility gaps</h2>
                <GapPanel onStudy={setStudy} onReachability={updateReachability} />
              </Suspense>
            )}
            {(view === "evidence" || view === "report") && (
              <Suspense fallback={<p role="status">Loading…</p>}>
                {view === "evidence" && <h2 className="sr-only" ref={viewTitleRef} tabIndex={-1}>Sidewalk records that need review</h2>}
                <GroundTruthPanel
                  key={view}
                  mode={view}
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
              <a href="/#methodology">Data & limits</a>
            </footer>
          </div>
        </div>
      </aside>
      <div className="sr-only" role="status" aria-live="polite">{status}</div>
    </main>
  );
}
