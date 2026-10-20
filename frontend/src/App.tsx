import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { lazy, Suspense } from "react";
import OriginSearch from "./OriginSearch";
import StopService from "./StopService";
import type { GapDetail } from "./GapPanel";
const GapPanel = lazy(() => import("./GapPanel"));
const MapView = lazy(() => import("./MapView"));
const GroundTruthPanel = lazy(() => import("./GroundTruthPanel"));
import type { Coverage, RouteResult, Stop } from "./types";
import { plannerData, PREPARED, warmRouting } from "./data";

const API =
  import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD ? "" : "http://localhost:8000");
const METERS_PER_MILE = 1609.344;
const algorithms = [
  {
    value: "dijkstra",
    label: "Dijkstra",
    description: "Finds the lowest-cost route for your walking preference.",
  },
  {
    value: "bidirectional_dijkstra",
    label: "Bidirectional Dijkstra",
    description: "Searches from both ends for the same lowest-cost objective.",
  },
  {
    value: "astar",
    label: "A*",
    description:
      "Uses distance to the stop to guide the search toward a lowest-cost route.",
  },
  {
    value: "bellman_ford",
    label: "Bellman–Ford",
    description:
      "Finds a lowest-cost route by relaxing edges. Usually slower on large networks.",
  },
  {
    value: "breadth_first",
    label: "Breadth-first search",
    description:
      "Chooses the fewest network segments. The walking distance may be longer.",
  },
];
type RouteKey = {
  origin: [number, number];
  stopId: string;
  algorithm: string;
  profile: string;
};

function distanceM(a: [number, number], b: [number, number]) {
  const rad = (value: number) => (value * Math.PI) / 180;
  const dLat = rad(b[0] - a[0]);
  const dLon = rad(b[1] - a[1]);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(rad(a[0])) * Math.cos(rad(b[0])) * Math.sin(dLon / 2) ** 2;
  return 6371000 * 2 * Math.asin(Math.sqrt(h));
}

function insideRing(point: [number, number], ring: number[][]) {
  const [latitude, longitude] = point;
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    const crosses =
      yi > latitude !== yj > latitude &&
      longitude < ((xj - xi) * (latitude - yi)) / (yj - yi) + xi;
    if (crosses) inside = !inside;
  }
  return inside;
}

function insideCoverage(point: [number, number], coverage: Coverage) {
  if (!coverage.boundary)
    return (
      distanceM([coverage.center.latitude, coverage.center.longitude], point) <=
      coverage.radius_m
    );
  const polygons =
    coverage.boundary.type === "Polygon"
      ? [coverage.boundary.coordinates]
      : coverage.boundary.coordinates;
  return polygons.some(
    (polygon) =>
      insideRing(point, polygon[0]) &&
      !polygon.slice(1).some((ring) => insideRing(point, ring)),
  );
}

function messageForUser(message: string) {
  return message
    .replace(
      /\b(\d+(?:\.\d+)?)\s*(?:kilometers?|kilometres?|km)\b/g,
      (_, value: string) => `${(Number(value) / 1.609344).toFixed(2)} mi`,
    )
    .replace(
      /\b(\d+(?:\.\d+)?)\s*(?:meters?|metres?|m)\b/g,
      (_, value: string) =>
        `${(Number(value) / METERS_PER_MILE).toFixed(2)} mi`,
    );
}

function detailOf(data: unknown) {
  const detail = (data as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return messageForUser(detail);
  if (detail && typeof detail === "object") {
    const fields = detail as {
      message?: string;
      initialization_error?: string;
    };
    return messageForUser(
      fields.message ||
        fields.initialization_error ||
        "The request could not be completed.",
    );
  }
  return "The request could not be completed.";
}

function readError(error: unknown) {
  return error instanceof Error
    ? messageForUser(error.message)
    : "Something went wrong. Try again.";
}

export default function App() {
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [stops, setStops] = useState<Stop[]>([]);
  const [origin, setOrigin] = useState<[number, number] | null>(null);
  const [destination, setDestination] = useState<Stop | null>(null);
  const [algorithm, setAlgorithm] = useState("astar");
  const [profile, setProfile] = useState("wheelchair");
  const [tab, setTab] = useState<"route" | "gaps" | "evidence">(
    new URLSearchParams(location.search).get("view") === "gaps"
      ? "gaps"
      : "route",
  );
  const [study, setStudy] = useState<GapDetail | null>(null);
  const [comparison, setComparison] = useState<{
    standard: RouteResult;
    alternative: RouteResult | null;
    extra_distance_m: number | null;
    extra_minutes: number | null;
    unavailable_reason?: string;
  } | null>(null);
  const [comparing, setComparing] = useState(false);
  const [benchmark, setBenchmark] = useState<
    Array<{
      algorithm: string;
      computation_time_ms?: number;
      distance_m?: number;
      error?: string;
    }>
  >([]);
  const [benchmarking, setBenchmarking] = useState(false);
  const [result, setResult] = useState<RouteResult | null>(null);
  const [resultKey, setResultKey] = useState<RouteKey | null>(null);
  const [loading, setLoading] = useState(true);
  const [mapReady, setMapReady] = useState(false);
  const [dataReady, setDataReady] = useState(false);
  const [routingWarm, setRoutingWarm] = useState(!PREPARED);
  const [calculating, setCalculating] = useState(false);
  const [mapMode, setMapMode] = useState<"idle" | "origin" | "report">("idle");
  const selecting = mapMode !== "idle";
  const reportPlacement = mapMode === "report";
  const [searchText, setSearchText] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [panelExpanded, setPanelExpanded] = useState(true);
  const [evidenceFeatures, setEvidenceFeatures] = useState<
    GeoJSON.FeatureCollection<GeoJSON.Point>
  >({ type: "FeatureCollection", features: [] });
  const [sidewalkFeatures, setSidewalkFeatures] =
    useState<GeoJSON.FeatureCollection>({
      type: "FeatureCollection",
      features: [],
    });
  const [reportPoint, setReportPoint] = useState<[number, number] | null>(null);
  const [candidateFocus, setCandidateFocus] = useState<[number, number] | null>(
    null,
  );
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(
    null,
  );
  const searchRef = useRef<HTMLInputElement>(null);
  const dataLoadRef = useRef<Promise<void> | null>(null);
  const requestRef = useRef<AbortController | null>(null);
  const compareRef = useRef<AbortController | null>(null);
  const inFlightRef = useRef(false);

  const loadData = useCallback(() => {
    if (dataLoadRef.current) return dataLoadRef.current;
    setLoading(true);
    setError("");
    const request = (async () => {
      try {
        if (PREPARED) void warmRouting().then(setRoutingWarm);
        const { coverage: nextCoverage, stops: loadedStops } =
          await plannerData();
        const stopData = { stops: loadedStops };
        setCoverage(nextCoverage);
        setStops(stopData.stops);
        const params = new URLSearchParams(location.search);
        const sharedStop = stopData.stops.find(
          (s) => s.stop_id === params.get("stop"),
        );
        const lat = Number(params.get("lat")),
          lon = Number(params.get("lon"));
        if (sharedStop) setDestination(sharedStop);
        if (
          params.has("lat") &&
          params.has("lon") &&
          Number.isFinite(lat) &&
          Number.isFinite(lon) &&
          insideCoverage([lat, lon], nextCoverage)
        )
          setOrigin([lat, lon]);
        if (
          ["standard", "wheelchair", "stroller", "low_vision"].includes(
            params.get("profile") || "",
          )
        )
          setProfile(params.get("profile")!);
        setDataReady(true);
        setStatus(
          `${stopData.stops.length} VTA stops loaded for ${nextCoverage.region || "the study area"}`,
        );
      } catch (nextError) {
        setDataReady(false);
        setError(
          nextError instanceof TypeError
            ? "TransitGap could not reach the transit and walking data service. Check your connection, then try again."
            : readError(nextError),
        );
        setStatus("Map is available. Route data needs attention.");
      } finally {
        setLoading(false);
        dataLoadRef.current = null;
      }
    })();
    dataLoadRef.current = request;
    return request;
  }, []);

  useEffect(() => {
    void loadData();
    return () => requestRef.current?.abort();
  }, [loadData]);

  const currentKey = useMemo<RouteKey | null>(() => {
    if (!origin || !destination) return null;
    return { origin, stopId: destination.stop_id, algorithm, profile };
  }, [origin, destination, algorithm, profile]);
  const resultIsStale = Boolean(
    result &&
      (!resultKey ||
        !currentKey ||
        resultKey.stopId !== currentKey.stopId ||
        resultKey.algorithm !== currentKey.algorithm ||
        resultKey.profile !== currentKey.profile ||
        resultKey.origin[0] !== currentKey.origin[0] ||
        resultKey.origin[1] !== currentKey.origin[1]),
  );
  const canRoute = dataReady && Boolean(origin && destination) && !calculating;

  const nearbyStops = useMemo(() => {
    const query = searchText.trim().toLocaleLowerCase();
    const center: [number, number] = origin || [
      coverage?.center.latitude ?? 37.3296,
      coverage?.center.longitude ?? -121.903,
    ];
    return stops
      .filter(
        (stop) => !query || stop.stop_name.toLocaleLowerCase().includes(query),
      )
      .map((stop) => ({
        stop,
        distance: distanceM(center, [stop.latitude, stop.longitude]),
      }))
      .sort(
        (a, b) =>
          a.distance - b.distance ||
          a.stop.stop_name.localeCompare(b.stop.stop_name),
      )
      .slice(0, query ? 8 : 4);
  }, [coverage, origin, searchText, stops]);

  const cancelRouteRequest = () => {
    requestRef.current?.abort();
    requestRef.current = null;
    inFlightRef.current = false;
    setCalculating(false);
  };

  const setStart = (point: [number, number]) => {
    if (coverage && !insideCoverage(point, coverage)) {
      setError(
        `That point is outside the supported ${coverage.region || "study"} area. Choose a point inside the dotted map boundary.`,
      );
      setStatus("Starting point was not changed");
      setPanelExpanded(true);
      return;
    }
    cancelRouteRequest();
    setOrigin(point);
    setCandidateFocus(point);
    setMapMode("idle");
    setPanelExpanded(true);
    setError("");
    setStatus("Starting point selected");
  };

  const chooseOnMap = () => {
    setMapMode("origin");
    setPanelExpanded(false);
    setError("");
    setStatus(
      "Choose a point inside the dotted map boundary. Press Escape to cancel.",
    );
  };

  const cancelMapSelection = useCallback(() => {
    setMapMode("idle");
    setPanelExpanded(true);
    setStatus("Map selection cancelled");
  }, []);

  useEffect(() => {
    if (mapMode === "idle") return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        cancelMapSelection();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mapMode, cancelMapSelection]);

  const useMyLocation = () => {
    setError("");
    if (!navigator.geolocation) {
      setError(
        "Location is not available in this browser. Choose a point on the map instead.",
      );
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) =>
        setStart([position.coords.latitude, position.coords.longitude]),
      (geoError) =>
        setError(
          geoError.code === 1
            ? "Location access was denied. Choose a point on the map instead."
            : geoError.code === 2
              ? "Your location could not be found. Choose a point on the map instead."
              : "The location request timed out. Try again or choose a point on the map.",
        ),
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 },
    );
  };

  const chooseStop = (stop: Stop) => {
    cancelRouteRequest();
    setDestination(stop);
    setMapMode("idle");
    setPanelExpanded(true);
    setSearchText("");
    setSearchOpen(false);
    setError("");
    setStatus(`Destination selected: ${stop.stop_name}`);
  };

  const clearStart = () => {
    cancelRouteRequest();
    setOrigin(null);
    setMapMode("idle");
    setError("");
    setStatus("Choose a new starting point");
  };

  const calculate = async () => {
    if (!origin || !destination || !dataReady || inFlightRef.current) return;
    const key: RouteKey = {
      origin,
      stopId: destination.stop_id,
      algorithm,
      profile,
    };
    const controller = new AbortController();
    requestRef.current = controller;
    inFlightRef.current = true;
    setCalculating(true);
    setError("");
    try {
      const response = await fetch(`${API}/route`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          origin_latitude: origin[0],
          origin_longitude: origin[1],
          destination_stop_id: destination.stop_id,
          algorithm,
          profile,
        }),
        signal: controller.signal,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(detailOf(data));
      if (controller.signal.aborted) return;
      setResult(data as RouteResult);
      setResultKey(key);
      setStatus("Route calculated on the mapped walking network");
      setPanelExpanded(true);
    } catch (nextError) {
      if (!controller.signal.aborted) {
        setError(
          nextError instanceof TypeError
            ? "TransitGap could not reach the routing service. Check your connection and try again."
            : readError(nextError),
        );
        setStatus("Route could not be calculated");
      }
    } finally {
      if (requestRef.current === controller) {
        requestRef.current = null;
        inFlightRef.current = false;
        setCalculating(false);
      }
    }
  };

  const reset = () => {
    cancelRouteRequest();
    setOrigin(null);
    setDestination(null);
    setSearchText("");
    setSearchOpen(false);
    setMapMode("idle");
    setResult(null);
    setResultKey(null);
    setError("");
    setStatus(
      dataReady
        ? `${stops.length} VTA stops loaded for ${coverage?.region || "the study area"}`
        : "Route data unavailable",
    );
    setPanelExpanded(true);
  };

  const routeFeature = useMemo(
    () =>
      result && !resultIsStale
        ? {
            type: "Feature" as const,
            properties: {},
            geometry: result.geometry,
          }
        : null,
    [result, resultIsStale],
  );
  const routeSegments = useMemo<GeoJSON.FeatureCollection>(
    () => ({
      type: "FeatureCollection",
      features:
        result && !resultIsStale
          ? (result.segments || []).map((segment) => ({
              type: "Feature",
              properties: { status: segment.status },
              geometry: segment.geometry,
            }))
          : [],
    }),
    [result, resultIsStale],
  );
  const comparisonGeometry = useMemo<GeoJSON.FeatureCollection>(
    () => ({
      type: "FeatureCollection",
      features:
        comparison && !resultIsStale
          ? [
              {
                type: "Feature",
                properties: {},
                geometry: comparison.standard.geometry,
              },
            ]
          : [],
    }),
    [comparison, resultIsStale],
  );
  const studyGeometry = useMemo<GeoJSON.FeatureCollection>(
    () => ({
      type: "FeatureCollection",
      features:
        study && tab === "gaps"
          ? [
              {
                type: "Feature",
                properties: { profile: "standard" },
                geometry: study.standard.geometry,
              },
              {
                type: "Feature",
                properties: { profile: "wheelchair" },
                geometry: study.wheelchair.geometry,
              },
            ]
          : [],
    }),
    [study, tab],
  );
  const studyFocus = useMemo<[number, number] | null>(
    () =>
      study && tab === "gaps"
        ? [study.latitude, study.longitude]
        : candidateFocus,
    [study, tab, candidateFocus],
  );
  useEffect(() => {
    setComparison(null);
    setBenchmark([]);
    compareRef.current?.abort();
    setComparing(false);
  }, [origin, destination, profile]);
  const showEvidence = useCallback(
    (
      gaps: GeoJSON.FeatureCollection<GeoJSON.Point>,
      sidewalks: GeoJSON.FeatureCollection,
    ) => {
      setEvidenceFeatures(gaps);
      setSidewalkFeatures(sidewalks);
    },
    [],
  );
  async function compare() {
    if (!origin || !destination) return;
    const controller = new AbortController();
    compareRef.current = controller;
    setComparing(true);
    setError("");
    try {
      const response = await fetch(`${API}/compare`, {
        signal: controller.signal,
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          origin_latitude: origin[0],
          origin_longitude: origin[1],
          destination_stop_id: destination.stop_id,
          profile,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw Error(detailOf(data));
      if (controller.signal.aborted) return;
      setComparison(data);
      const route = data.alternative || data.standard;
      setResult(route);
      setResultKey({
        origin,
        stopId: destination.stop_id,
        algorithm: route.algorithm,
        profile,
      });
      setAlgorithm(route.algorithm);
    } catch (e) {
      if (!controller.signal.aborted) setError(readError(e));
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
        body: JSON.stringify({
          origin_latitude: origin[0],
          origin_longitude: origin[1],
          destination_stop_id: destination.stop_id,
          profile,
        }),
      });
      const data = await r.json();
      if (!r.ok) throw Error(detailOf(data));
      setBenchmark(data.results);
    } catch (e) {
      setError(readError(e));
    } finally {
      setBenchmarking(false);
    }
  }
  function share() {
    if (!origin || !destination) return;
    const url = new URL("/app", location.origin);
    url.search = new URLSearchParams({
      lat: String(origin[0]),
      lon: String(origin[1]),
      stop: destination.stop_id,
      profile,
    }).toString();
    history.replaceState(null, "", url);
    void navigator.clipboard
      ?.writeText(url.href)
      .then(() => setStatus("Journey link copied"))
      .catch(() => setStatus("Journey link is in the address bar"));
  }

  const handleMapOrigin = useCallback(
    (point: [number, number]) => {
      if (reportPlacement) {
        setReportPoint(point);
        setMapMode("idle");
        setPanelExpanded(true);
        setStatus("Report location selected");
        return;
      }
      setStart(point);
    },
    [reportPlacement, setStart],
  );

  return (
    <main className={`app-shell ${panelExpanded ? "" : "sheet-is-collapsed"}`}>
      <section className="map-shell" aria-label="Map">
        <Suspense fallback={null}>
          <MapView
            coverage={coverage}
            stops={stops}
            origin={origin}
            destination={destination}
            route={routeFeature}
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
              setTab("evidence");
              setPanelExpanded(true);
            }}
            reportPoint={reportPoint}
          />
        </Suspense>
        <details className="map-legend">
          <summary>Map key</summary>
          <span>A · Your start</span>
          <span>B · VTA stop</span>
          <span className="legend-mapped">Solid green: mapped attributes</span>
          <span className="legend-unknown">
            Dashed grey: missing information
          </span>
          <span className="legend-concern">Orange: mapped concern</span>
          <span>Grey outline: standard comparison</span>
        </details>
        {selecting && (
          <div className="map-selection-banner" role="status">
            <span>
              {reportPlacement
                ? "Tap to place a report"
                : "Tap to choose your start"}
            </span>
            <button type="button" onClick={cancelMapSelection}>
              Cancel<span className="sr-only"> map selection</span>
            </button>
          </div>
        )}
        {(!mapReady || loading) && (
          <div className="map-loading" role="status">
            <span className="spinner" />
            {!mapReady ? "Preparing map…" : "Loading transit data…"}
          </div>
        )}
      </section>
      <aside
        className={`panel ${panelExpanded ? "panel-expanded" : "panel-collapsed"}`}
        aria-label="Route planner"
      >
        <div className="panel-scroll">
          <header className="panel-header">
            <a className="brand-lockup" href="/" aria-label="TransitGap home">
              <h1>TransitGap</h1>
            </a>
            <button
              className="mobile-panel-toggle icon-button"
              onClick={() => setPanelExpanded(!panelExpanded)}
              aria-label={
                panelExpanded
                  ? "Collapse route planner"
                  : "Expand route planner"
              }
              aria-expanded={panelExpanded}
            >
              {panelExpanded ? (
                <ChevronDown size={20} />
              ) : (
                <ChevronUp size={20} />
              )}
            </button>
          </header>
          <nav className="app-tabs" aria-label="Map views">
            {(["route", "gaps", "evidence"] as const).map((value) => (
              <button
                key={value}
                aria-current={tab === value ? "page" : undefined}
                onClick={() => setTab(value)}
              >
                {value === "route"
                  ? "Route"
                  : value === "gaps"
                    ? "Access gaps"
                    : "Evidence"}
              </button>
            ))}
          </nav>
          <div className="panel-content">
            {error && (
              <div className="notice error" role="alert">
                <span>{error}</span>
                {!dataReady && !loading && (
                  <button
                    className="text-button"
                    onClick={() => void loadData()}
                  >
                    Try again
                  </button>
                )}
              </div>
            )}
            <span
              className={`dataset-status ${dataReady ? "is-ready" : ""}`}
              role="status"
            >
              {loading
                ? "Loading…"
                : dataReady
                  ? `${stops.length.toLocaleString()} VTA stops`
                  : "Data unavailable"}
            </span>
            {tab === "route" && (
              <>
                <section
                  className="step-section"
                  aria-labelledby="origin-title"
                >
                  <h2 id="origin-title">Where are you starting?</h2>
                  {origin && (
                    <div className="selection-card">
                      <strong>
                        {origin[0].toFixed(5)}, {origin[1].toFixed(5)}
                      </strong>
                      <button
                        className="change-stop"
                        onClick={clearStart}
                        aria-label="Change starting point"
                      >
                        Clear
                      </button>
                    </div>
                  )}
                  <div className="origin-actions">
                    <button
                      className="button"
                      onClick={
                        mapMode === "origin" ? cancelMapSelection : chooseOnMap
                      }
                    >
                      {mapMode === "origin"
                        ? "Cancel choosing start"
                        : "Choose on map"}
                    </button>
                    <button className="button" onClick={useMyLocation}>
                      Use my location
                    </button>
                  </div>
                  <OriginSearch
                    onChoose={(point) => {
                      setStart(point);
                      setCandidateFocus(point);
                    }}
                  />
                </section>
                <section
                  className="step-section destination-section"
                  aria-labelledby="destination-title"
                >
                  <h2 id="destination-title">Which VTA stop?</h2>
                  {destination && (
                    <div className="selected-stop">
                      <span className="destination-pin">B</span>
                      <strong>{destination.stop_name}</strong>
                      <button
                        className="change-stop"
                        onClick={() => {
                          setDestination(null);
                          setSearchOpen(true);
                          requestAnimationFrame(() =>
                            searchRef.current?.focus(),
                          );
                        }}
                      >
                        Change
                      </button>
                    </div>
                  )}
                  <label className="search-box" htmlFor="stop-search">
                    <input
                      ref={searchRef}
                      id="stop-search"
                      type="search"
                      aria-label="Search VTA stops"
                      value={searchText}
                      placeholder="Search stops by name"
                      autoComplete="off"
                      onFocus={() => setSearchOpen(true)}
                      onChange={(e) => {
                        setSearchText(e.target.value);
                        setSearchOpen(true);
                      }}
                      aria-controls={searchOpen ? "stop-results" : undefined}
                    />
                  </label>
                  {searchOpen && (
                    <div
                      className="stop-results"
                      id="stop-results"
                      aria-label="VTA stop results"
                    >
                      {nearbyStops.map(({ stop, distance }) => (
                        <button
                          className="stop-option"
                          key={stop.stop_id}
                          onClick={() => chooseStop(stop)}
                        >
                          <span>{stop.stop_name}</span>
                          <span>
                            {(distance / METERS_PER_MILE).toFixed(2)} mi
                          </span>
                        </button>
                      ))}
                      {nearbyStops.length === 0 && <p>No matching stops.</p>}
                    </div>
                  )}
                  {destination && <StopService id={destination.stop_id} />}
                </section>
                <section className="step-section profile-section">
                  <label htmlFor="mobility-profile">Travel profile</label>
                  <select
                    id="mobility-profile"
                    aria-label="Route profile"
                    value={profile}
                    onChange={(e) => setProfile(e.target.value)}
                  >
                    <option value="standard">Standard</option>
                    <option value="wheelchair">Wheelchair</option>
                    <option value="stroller">Stroller</option>
                    <option value="low_vision">Low vision</option>
                    <option value="prefer_documented_paths">
                      Prefer documented paths
                    </option>
                  </select>
                </section>
                <div className="route-actions">
                  <button
                    className="button button-primary find-route"
                    disabled={!canRoute}
                    onClick={() => void calculate()}
                    aria-busy={calculating}
                  >
                    {calculating ? (
                      <>
                        <span className="spinner light" />
                        {routingWarm
                          ? "Finding route…"
                          : "Preparing county routing…"}
                      </>
                    ) : (
                      "Find Route"
                    )}
                  </button>
                  {(result || origin) && (
                    <button
                      className="button"
                      onClick={() => {
                        reset();
                        setComparison(null);
                      }}
                    >
                      Reset
                    </button>
                  )}
                </div>
                {!origin && (
                  <button
                    className="example-link"
                    disabled={!dataReady}
                    onClick={() => {
                      const stop = stops.find(
                        (s) => s.stop_name === "San Jose Diridon (Bay 11)",
                      );
                      if (stop) {
                        setStart([37.32875, -121.90442]);
                        chooseStop(stop);
                      }
                    }}
                  >
                    Try a real Diridon journey
                  </button>
                )}
                {result && (
                  <section
                    className={`route-result ${resultIsStale ? "route-result-stale" : ""}`}
                    aria-live="polite"
                    aria-label="Route details"
                  >
                    <h2>{result.destination.stop_name}</h2>
                    {resultIsStale ? (
                      <p>Journey changed. Find the route again.</p>
                    ) : (
                      <>
                        <div className="route-metrics">
                          <strong>
                            {(result.distance_m / METERS_PER_MILE).toFixed(2)}{" "}
                            mi
                          </strong>
                          <strong>
                            {Math.max(
                              1,
                              Math.round(result.duration_seconds / 60),
                            )}{" "}
                            min
                          </strong>
                        </div>
                        <p>
                          Time estimate assumes{" "}
                          {(result.walking_speed_mps_assumed * 2.23694).toFixed(
                            1,
                          )}{" "}
                          mph.
                        </p>
                        {result.algorithm_warning && (
                          <p role="status">{result.algorithm_warning}</p>
                        )}
                        {result.data_confidence != null && (
                          <p>
                            {Math.round(result.data_confidence * 100)}% of
                            applicable accessibility attributes documented,
                            weighted by route length. Mapped, not field checked.
                          </p>
                        )}
                        <button
                          className="button"
                          onClick={() => void compare()}
                          disabled={comparing || profile === "standard"}
                        >
                          {comparing
                            ? "Comparing…"
                            : "Compare with standard route"}
                        </button>
                        {comparison && (
                          <div
                            className="mobility-comparison"
                            aria-label="Mobility detour"
                          >
                            {comparison.alternative ? (
                              <>
                                <h3>Mobility detour</h3>
                                <p>
                                  {(
                                    (comparison.extra_distance_m || 0) /
                                    METERS_PER_MILE
                                  ).toFixed(2)}{" "}
                                  mi farther ·{" "}
                                  {(comparison.extra_minutes || 0).toFixed(1)}{" "}
                                  min difference.
                                </p>
                                <p>
                                  Includes different speed assumptions. Grey is
                                  the standard route; the coloured line is your
                                  profile.
                                </p>
                              </>
                            ) : (
                              <p>{comparison.unavailable_reason}</p>
                            )}
                          </div>
                        )}
                        <details className="plain-details">
                          <summary>Directions</summary>
                          <ol className="directions">
                            {result.directions?.map((step, i) => (
                              <li key={i}>
                                {step.instruction} ·{" "}
                                {(step.distance_m / METERS_PER_MILE).toFixed(2)}{" "}
                                mi
                                {step.status !== "mapped" && (
                                  <details>
                                    <summary>
                                      {step.status === "concern"
                                        ? "Mapped concern"
                                        : "Information missing"}
                                    </summary>
                                    <ul>
                                      {step.warnings.map((w) => (
                                        <li key={w}>{w}</li>
                                      ))}
                                    </ul>
                                  </details>
                                )}
                              </li>
                            ))}
                          </ol>
                        </details>
                        <details className="plain-details">
                          <summary>Route evidence</summary>
                          <p>{result.accessibility_warning}</p>
                          <p>{result.groundtruth_evidence?.message}</p>
                          {result.accessibility && (
                            <dl>
                              <div>
                                <dt>Crossings with kerb records</dt>
                                <dd>
                                  {
                                    result.accessibility.crossing_observations
                                      .known_kerb_information
                                  }{" "}
                                  /{" "}
                                  {
                                    result.accessibility.crossing_observations
                                      .denominator
                                  }
                                </dd>
                              </div>
                              <div>
                                <dt>Mapped stair segments</dt>
                                <dd>{result.mapped_stair_segments}</dd>
                              </div>
                            </dl>
                          )}
                        </details>
                        <button className="example-link" onClick={share}>
                          Copy journey link
                        </button>
                      </>
                    )}
                  </section>
                )}
                <details className="advanced-settings">
                  <summary>
                    Under the hood <ChevronDown size={15} />
                  </summary>
                  <label htmlFor="algorithm">Routing algorithm</label>
                  <select
                    id="algorithm"
                    value={algorithm}
                    onChange={(e) => setAlgorithm(e.target.value)}
                  >
                    {algorithms.map((item) => (
                      <option value={item.value} key={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                  <p>
                    {algorithms.find((a) => a.value === algorithm)?.description}
                  </p>
                  <button
                    className="button"
                    onClick={() => void runBenchmark()}
                    disabled={!origin || !destination || benchmarking}
                  >
                    {benchmarking
                      ? "Measuring…"
                      : "Compare all five algorithms"}
                  </button>
                  {benchmark.length > 0 && (
                    <>
                      <table className="benchmark-table">
                        <thead>
                          <tr>
                            <th>Algorithm</th>
                            <th>ms</th>
                            <th>mi</th>
                          </tr>
                        </thead>
                        <tbody>
                          {benchmark.map((row) => (
                            <tr key={row.algorithm}>
                              <th>
                                {
                                  algorithms.find(
                                    (a) => a.value === row.algorithm,
                                  )?.label
                                }
                              </th>
                              <td>
                                {row.computation_time_ms?.toFixed(1) ||
                                  row.error}
                              </td>
                              <td>
                                {row.distance_m != null
                                  ? (row.distance_m / METERS_PER_MILE).toFixed(
                                      2,
                                    )
                                  : "Unavailable"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      <p>
                        Measured per request, including route reconstruction.
                        BFS minimizes segments, not distance.
                      </p>
                    </>
                  )}
                </details>
                <p className="route-safety">
                  Mapped routes are not verified accessible. Missing tags and
                  changing conditions can affect a journey.
                </p>
              </>
            )}
            {tab === "gaps" && (
              <Suspense fallback={<p role="status">Loading access study…</p>}>
                <GapPanel onStudy={setStudy} />
              </Suspense>
            )}
            {tab === "evidence" && (
              <Suspense fallback={<p role="status">Loading evidence…</p>}>
                <GroundTruthPanel
                  onFeatures={showEvidence}
                  onClearReportPoint={() => setReportPoint(null)}
                  onRequestLocation={() => {
                    setMapMode("report");
                    setPanelExpanded(false);
                  }}
                  reportPoint={reportPoint}
                  onFocusCandidate={(point) => {
                    setCandidateFocus(point);
                    setSelectedCandidateId(null);
                  }}
                  selectedCandidateId={selectedCandidateId}
                />
              </Suspense>
            )}
            <footer className="panel-footer">
              <a href="https://www.openstreetmap.org/copyright">
                OpenStreetMap
              </a>
              <a href="https://www.vta.org/go/developers">VTA GTFS</a>
              <a href="/#methodology">Data & limits</a>
            </footer>
          </div>
        </div>
      </aside>
      <div className="sr-only" role="status" aria-live="polite">
        {status}
      </div>
    </main>
  );
}
