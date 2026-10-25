import { useEffect, useRef } from "react";
import "maplibre-gl/dist/maplibre-gl.css";
import * as maplibregl from "maplibre-gl";
import {
  type Map,
  type Marker,
  setWorkerUrl,
  setWorkerCount,
} from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import type { Coverage, Stop } from "./types";

setWorkerUrl(workerUrl);
setWorkerCount(2);

type RouteFeature = GeoJSON.Feature<GeoJSON.Geometry> | null;
type Props = {
  coverage: Coverage | null;
  stops: Stop[];
  origin: [number, number] | null;
  destination: Stop | null;
  route: RouteFeature;
  segments: GeoJSON.FeatureCollection;
  comparison: GeoJSON.FeatureCollection;
  study: GeoJSON.FeatureCollection;
  selecting: boolean;
  panelExpanded: boolean;
  onReady: () => void;
  onOrigin: (point: [number, number]) => void;
  onStop: (stop: Stop) => void;
  evidence: GeoJSON.FeatureCollection<GeoJSON.Point>;
  sidewalks: GeoJSON.FeatureCollection;
  focusPoint: [number, number] | null;
  onCandidate: (candidateId: string) => void;
  reportPoint: [number, number] | null;
  routeActive: boolean;
  showStops: boolean;
  advocateStops: GeoJSON.FeatureCollection<GeoJSON.Point>;
  showAdvocateStops: boolean;
  onViewChange?: (center: [number, number]) => void;
};

// Default to Santa Clara city center with nearby rail and VTA stops in view.
// A previously granted location can still recenter the map.
const center: [number, number] = [-121.9552, 37.3541];
const diridonPilotCenter: [number, number] = [-121.903, 37.3296];
const diridonPilotRadiusM = 1500;

function circleGeometry(centerPoint: [number, number], radiusM: number): GeoJSON.Polygon {
  const [longitude, latitude] = centerPoint;
  const points: number[][] = [];
  for (let i = 0; i <= 96; i += 1) {
    const angle = (i * Math.PI) / 48;
    points.push([
      longitude + (radiusM / (111320 * Math.cos((latitude * Math.PI) / 180))) * Math.sin(angle),
      latitude + (radiusM / 111320) * Math.cos(angle),
    ]);
  }
  return { type: "Polygon", coordinates: [points] };
}

function stopFeatures(
  stops: Stop[],
  selectedId: string | undefined,
): GeoJSON.FeatureCollection<GeoJSON.Point> {
  return {
    type: "FeatureCollection",
    features: stops.map((stop) => ({
      type: "Feature",
      id: stop.stop_id,
      properties: {
        stop_id: stop.stop_id,
        stop_name: stop.stop_name,
        agency: stop.agency_name || stop.agency || "VTA",
        selected: stop.stop_id === selectedId,
      },
      geometry: { type: "Point", coordinates: [stop.longitude, stop.latitude] },
    })),
  };
}

/** Midpoints of segments with documented concerns (not merely missing data). */
function concernPoints(
  segments: GeoJSON.FeatureCollection,
): GeoJSON.FeatureCollection<GeoJSON.Point> {
  return {
    type: "FeatureCollection",
    features: segments.features
      .filter((feature) => feature.properties?.concern && feature.geometry.type === "LineString")
      .map((feature) => {
        const coords = (feature.geometry as GeoJSON.LineString).coordinates;
        return {
          type: "Feature" as const,
          properties: {},
          geometry: { type: "Point" as const, coordinates: coords[Math.floor(coords.length / 2)] },
        };
      }),
  };
}

function addCoverageLayer(map: Map, coverage: Coverage | null) {
  if (!coverage || map.getSource("coverage")) return;
  let geometry: GeoJSON.Geometry;
  if (coverage.boundary) {
    geometry = coverage.boundary as GeoJSON.Geometry;
  } else {
    const points: number[][] = [];
    for (let i = 0; i <= 72; i += 1) {
      const angle = (i * Math.PI) / 36;
      const latitude =
        coverage.center.latitude +
        (coverage.radius_m / 111320) * Math.cos(angle);
      const longitude =
        coverage.center.longitude +
        (coverage.radius_m /
          (111320 * Math.cos((coverage.center.latitude * Math.PI) / 180))) *
          Math.sin(angle);
      points.push([longitude, latitude]);
    }
    geometry = { type: "Polygon", coordinates: [points] };
  }
  map.addSource("coverage", {
    type: "geojson",
    data: { type: "Feature", properties: {}, geometry },
  });
  map.addLayer({
    id: "coverage-area",
    type: "fill",
    source: "coverage",
    paint: { "fill-color": "#176b5b", "fill-opacity": 0.025 },
  });
  map.addLayer({
    id: "coverage-edge-halo",
    type: "line",
    source: "coverage",
    paint: {
      "line-color": "#fffefa",
      "line-width": 5,
      "line-opacity": 0.95,
    },
  });
  map.addLayer({
    id: "coverage-edge",
    type: "line",
    source: "coverage",
    paint: {
      "line-color": "#176b5b",
      "line-width": 2.5,
      "line-dasharray": [2, 1.5],
      "line-opacity": 1,
    },
  });
  if (coverage.boundary) {
    map.addSource("diridon-pilot-area", {
      type: "geojson",
      data: { type: "Feature", properties: {}, geometry: circleGeometry(diridonPilotCenter, diridonPilotRadiusM) },
    });
    map.addLayer({
      id: "diridon-pilot-fill",
      type: "fill",
      source: "diridon-pilot-area",
      paint: { "fill-color": "#b45622", "fill-opacity": 0.035 },
    });
    map.addLayer({
      id: "diridon-pilot-edge",
      type: "line",
      source: "diridon-pilot-area",
      paint: { "line-color": "#b45622", "line-width": 2, "line-dasharray": [1, 1.5], "line-opacity": 0.95 },
    });
    map.addSource("diridon-pilot-label", {
      type: "geojson",
      data: {
        type: "Feature",
        properties: { label: "Diridon pilot · detailed sidewalk records" },
        geometry: { type: "Point", coordinates: diridonPilotCenter },
      },
    });
    map.addLayer({
      id: "diridon-pilot-label",
      type: "symbol",
      source: "diridon-pilot-label",
      layout: { "text-field": ["get", "label"], "text-font": ["Arial Bold"], "text-size": 12, "text-offset": [0, 1.2], "text-allow-overlap": false },
      paint: { "text-color": "#7a3b1d", "text-halo-color": "#fffefa", "text-halo-width": 2 },
    });
    map.addSource("coverage-label", {
      type: "geojson",
      data: {
        type: "Feature",
        properties: { label: "Santa Clara County route coverage" },
        geometry: { type: "Point", coordinates: [coverage.center.longitude, coverage.center.latitude] },
      },
    });
    map.addLayer({
      id: "coverage-label",
      type: "symbol",
      source: "coverage-label",
      minzoom: 0,
      maxzoom: 10.8,
      layout: { "text-field": ["get", "label"], "text-font": ["Arial Bold"], "text-size": 15, "text-allow-overlap": false },
      paint: { "text-color": "#0f5c4c", "text-halo-color": "#fffefa", "text-halo-width": 2.5 },
    });
  }
}

export default function MapView({
  coverage,
  stops,
  origin,
  destination,
  route,
  segments,
  comparison,
  study,
  selecting,
  panelExpanded,
  onReady,
  onOrigin,
  onStop,
  evidence,
  sidewalks,
  focusPoint,
  onCandidate,
  reportPoint,
  routeActive,
  showStops,
  advocateStops,
  showAdvocateStops,
  onViewChange,
}: Props) {
  const container = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);
  const originMarker = useRef<Marker | null>(null);
  const destinationMarker = useRef<Marker | null>(null);
  const reportMarker = useRef<Marker | null>(null);
  const handlers = useRef({ onOrigin, onStop, onCandidate, selecting, stops, onViewChange });
  const latest = useRef({ route, destination, panelExpanded, coverage });
  const evidenceRef = useRef({ evidence, sidewalks });

  useEffect(() => {
    handlers.current = { onOrigin, onStop, onCandidate, selecting, stops, onViewChange };
    latest.current = { route, destination, panelExpanded, coverage };
    evidenceRef.current = { evidence, sidewalks };
  }, [
    onOrigin,
    onStop,
    onCandidate,
    selecting,
    stops,
    onViewChange,
    route,
    destination,
    panelExpanded,
    coverage,
    evidence,
    sidewalks,
  ]);

  useEffect(() => {
    if (!container.current) return;
    const map = new maplibregl.Map({
      container: container.current,
      center,
      zoom: 13.2,
      minZoom: 8,
      maxZoom: 19,
      attributionControl: false,
      pixelRatio: Math.min(window.devicePixelRatio, 1.5),
      fadeDuration: 0,
      style: {
        version: 8,
        // Cluster counts use local fonts; no third-party glyph download needed.
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors",
          },
        },
        layers: [
          { id: "osm", type: "raster", source: "osm", minzoom: 0, maxzoom: 19 },
        ],
      },
    });
    map.addControl(
      new maplibregl.NavigationControl({
        showCompass: false,
        visualizePitch: false,
      }),
      "bottom-right",
    );
    map.addControl(
      new maplibregl.AttributionControl({ compact: true }),
      "bottom-right",
    );

    const addLayers = () => {
      addCoverageLayer(map, latest.current.coverage);
      if (!map.getSource("municipal-sidewalks")) {
        map.addSource("municipal-sidewalks", {
          type: "geojson",
          data: evidenceRef.current.sidewalks,
        });
        map.addLayer({
          id: "municipal-sidewalk-fill",
          type: "fill",
          source: "municipal-sidewalks",
          paint: { "fill-color": "#2f8f70", "fill-opacity": 0.23 },
        });
        map.addLayer({
          id: "municipal-sidewalk-outline",
          type: "line",
          source: "municipal-sidewalks",
          paint: {
            "line-color": "#26765d",
            "line-width": 0.8,
            "line-opacity": 0.7,
          },
        });
      }
      if (!map.getSource("evidence")) {
        map.addSource("evidence", {
          type: "geojson",
          data: evidenceRef.current.evidence,
        });
        map.addLayer({
          id: "evidence-points",
          type: "circle",
          source: "evidence",
          paint: {
            "circle-color": [
              "match",
              ["get", "classification"],
              "DOCUMENTED_IN_CITY_ONLY",
              "#c56c34",
              "NEEDS_REVIEW",
              "#b48832",
              "CONFLICTING_SOURCES",
              "#a64d49",
              "COMMUNITY_REPORTED",
              "#654fa0",
              "#566c9a",
            ],
            "circle-radius": 6,
            "circle-stroke-color": "#fff",
            "circle-stroke-width": 1.5,
          },
        });
      }
      if (!map.getSource("vta-stops")) {
        map.addSource("vta-stops", {
          type: "geojson",
          data: stopFeatures(
            handlers.current.stops,
            latest.current.destination?.stop_id,
          ),
          cluster: true,
          clusterRadius: 56,
          clusterMaxZoom: 12,
        });
        map.addLayer({
          id: "stop-clusters",
          type: "circle",
          source: "vta-stops",
          filter: ["has", "point_count"],
          paint: {
            "circle-color": "#fffefa",
            "circle-opacity": 0.92,
            "circle-radius": ["step", ["get", "point_count"], 10, 10, 12, 40, 14],
            "circle-stroke-color": "#176b5b",
            "circle-stroke-width": 1.5,
          },
        });
        map.addLayer({
          id: "stop-cluster-count",
          type: "symbol",
          source: "vta-stops",
          filter: ["has", "point_count"],
          layout: {
            "text-field": ["get", "point_count_abbreviated"],
            "text-font": ["Arial Bold"],
            "text-size": 10,
          },
          paint: { "text-color": "#176b5b" },
        });
        map.addLayer({
          id: "vta-stops",
          type: "circle",
          source: "vta-stops",
          filter: ["!", ["has", "point_count"]],
          paint: {
            "circle-color": ["case", ["get", "selected"], "#d58c2e", ["match", ["get", "agency"], "Caltrain", "#81502b", "BART", "#3c536d", "#176b5b"]],
            "circle-radius": ["case", ["get", "selected"], 9, ["match", ["get", "agency"], "VTA", 5, 7]],
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": ["case", ["get", "selected"], 3, 2],
            "circle-opacity": 0.98,
          },
        });
      }
      if (!map.getSource("advocate-stops")) {
        map.addSource("advocate-stops", { type: "geojson", data: advocateStops });
        map.addLayer({
          id: "advocate-stop-circles",
          type: "circle",
          source: "advocate-stops",
          paint: {
            "circle-color": "#b45622",
            "circle-radius": 13,
            "circle-stroke-color": "#fffefa",
            "circle-stroke-width": 2.5,
          },
          layout: { visibility: showAdvocateStops ? "visible" : "none" },
        });
        map.addLayer({
          id: "advocate-stop-ranks",
          type: "symbol",
          source: "advocate-stops",
          layout: {
            "text-field": ["get", "rank"],
            "text-font": ["Arial Bold"],
            "text-size": 11,
            "text-allow-overlap": true,
            "text-ignore-placement": true,
            visibility: showAdvocateStops ? "visible" : "none",
          },
          paint: { "text-color": "#ffffff" },
        });
      }
      if (!map.getSource("route")) {
        map.addSource("route", {
          type: "geojson",
          data: latest.current.route || {
            type: "Feature",
            properties: {},
            geometry: { type: "LineString", coordinates: [] },
          },
        });
        map.addSource("comparison", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });
        map.addLayer({
          id: "comparison-line",
          type: "line",
          source: "comparison",
          paint: {
            "line-color": "#6b7780",
            "line-width": 5,
            "line-opacity": 0.6,
          },
          layout: { "line-cap": "round", "line-join": "round" },
        });
        // One continuous, high-contrast walking line. Data uncertainty is
        // described in the panel; only unmapped connectors and documented
        // concerns are drawn separately, so the route stays easy to follow.
        map.addSource("route-segments", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });
        map.addLayer({
          id: "route-outline",
          type: "line",
          source: "route-segments",
          filter: ["!=", ["get", "kind"], "connector"],
          paint: { "line-color": "#ffffff", "line-width": 10 },
          layout: { "line-cap": "round", "line-join": "round" },
        });
        map.addLayer({
          id: "route-line",
          type: "line",
          source: "route-segments",
          filter: ["!=", ["get", "kind"], "connector"],
          paint: { "line-color": "#0f5c4c", "line-width": 6 },
          layout: { "line-cap": "round", "line-join": "round" },
        });
        map.addLayer({
          id: "route-connectors",
          type: "line",
          source: "route-segments",
          filter: ["==", ["get", "kind"], "connector"],
          paint: { "line-color": "#36423b", "line-width": 3, "line-dasharray": [1, 1.5] },
          layout: { "line-cap": "round" },
        });
        map.addSource("route-concerns", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });
        map.addLayer({
          id: "route-concerns",
          type: "circle",
          source: "route-concerns",
          paint: {
            "circle-color": "#b45622",
            "circle-radius": 6,
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 2,
          },
        });
        map.addSource("study", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });
        map.addLayer({
          id: "study-standard",
          type: "line",
          source: "study",
          filter: ["==", ["get", "profile"], "standard"],
          paint: {
            "line-color": "#637178",
            "line-width": 4,
            "line-opacity": 0.65,
          },
        });
        map.addLayer({
          id: "study-wheelchair",
          type: "line",
          source: "study",
          filter: ["==", ["get", "profile"], "wheelchair"],
          paint: { "line-color": "#176b5b", "line-width": 2.5 },
        });
        map.addLayer({
          id: "study-documented",
          type: "line",
          source: "study",
          filter: ["==", ["get", "profile"], "documented"],
          paint: { "line-color": "#176b5b", "line-width": 3, "line-opacity": 0.8 },
        });
        map.addLayer({
          id: "study-unknown",
          type: "line",
          source: "study",
          filter: ["==", ["get", "profile"], "unknown"],
          paint: { "line-color": "#98603a", "line-width": 3, "line-dasharray": [1.5, 1.5] },
        });
      }
    };

    map.on("load", () => {
      addLayers();
      if (container.current) container.current.dataset.mapState = "ready";
      onReady();
      map.on("click", (event) => {
        if (handlers.current.selecting) {
          handlers.current.onOrigin([event.lngLat.lat, event.lngLat.lng]);
          return;
        }
        const evidence = map.queryRenderedFeatures(event.point, {
          layers: ["evidence-points"],
        })[0];
        const candidateId = evidence?.properties?.id;
        if (typeof candidateId === "string" && candidateId.startsWith("gap:")) {
          handlers.current.onCandidate(candidateId);
          return;
        }
        const features = map.queryRenderedFeatures(event.point, {
          layers: ["vta-stops", "stop-clusters"],
        });
        const stopFeature = features.find(
          (feature) => feature.layer.id === "vta-stops",
        );
        const stop = handlers.current.stops.find(
          (item) => item.stop_id === stopFeature?.properties?.stop_id,
        );
        if (stop) {
          handlers.current.onStop(stop);
          return;
        }
        const cluster = features.find(
          (feature) => feature.layer.id === "stop-clusters",
        );
        const clusterId = cluster?.properties?.cluster_id;
        const source = map.getSource("vta-stops") as
          | maplibregl.GeoJSONSource
          | undefined;
        if (
          cluster &&
          clusterId !== undefined &&
          source &&
          cluster.geometry.type === "Point"
        ) {
          const clusterCenter = cluster.geometry.coordinates as [
            number,
            number,
          ];
          void source
            .getClusterExpansionZoom(Number(clusterId))
            .then((zoom) => {
              map.easeTo({ center: clusterCenter, zoom });
            })
            .catch(() => undefined);
          return;
        }
      });
      map.on("moveend", () => {
        const c = map.getCenter();
        handlers.current.onViewChange?.([c.lat, c.lng]);
      });
      let lastPointerQuery = 0;
      map.on("mousemove", (event) => {
        if (performance.now() - lastPointerQuery < 60) return;
        lastPointerQuery = performance.now();
        const features = map.queryRenderedFeatures(event.point, {
          layers: ["vta-stops", "stop-clusters"],
        });
        map.getCanvas().style.cursor = handlers.current.selecting
          ? "crosshair"
          : features.length
            ? "pointer"
            : "";
      });
    });
    mapRef.current = map;
    if (import.meta.env.DEV)
      (window as Window & { __transitGapMap?: Map }).__transitGapMap = map;

    const resizeMap = () => map.resize();
    const resizeObserver = new ResizeObserver(resizeMap);
    resizeObserver.observe(container.current);
    window.addEventListener("resize", resizeMap);

    return () => {
      resizeObserver.disconnect();
      window.removeEventListener("resize", resizeMap);
      originMarker.current?.remove();
      destinationMarker.current?.remove();
      reportMarker.current?.remove();
      originMarker.current = null;
      destinationMarker.current = null;
      reportMarker.current = null;
      if (
        import.meta.env.DEV &&
        (window as Window & { __transitGapMap?: Map }).__transitGapMap === map
      )
        delete (window as Window & { __transitGapMap?: Map }).__transitGapMap;
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      (
        map.getSource("evidence") as maplibregl.GeoJSONSource | undefined
      )?.setData(evidence);
      (
        map.getSource("municipal-sidewalks") as
          | maplibregl.GeoJSONSource
          | undefined
      )?.setData(sidewalks);
    };
    if (map.isStyleLoaded()) apply();
    else map.once("load", apply);
  }, [evidence, sidewalks]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      (
        map.getSource("route-segments") as maplibregl.GeoJSONSource | undefined
      )?.setData(segments);
      (
        map.getSource("route-concerns") as maplibregl.GeoJSONSource | undefined
      )?.setData(concernPoints(segments));
      (
        map.getSource("comparison") as maplibregl.GeoJSONSource | undefined
      )?.setData(comparison);
      (map.getSource("study") as maplibregl.GeoJSONSource | undefined)?.setData(
        study,
      );
    };
    if (map.getSource("route-segments")) apply();
    else map.once("load", apply);
    return () => {
      map.off("load", apply);
    };
  }, [segments, comparison, study]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !coverage) return;
    const updateCoverage = () => addCoverageLayer(map, coverage);
    if (map.getSource("vta-stops")) updateCoverage();
    else map.once("load", updateCoverage);
  }, [coverage]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      (map.getSource("advocate-stops") as maplibregl.GeoJSONSource | undefined)?.setData(advocateStops);
      for (const layer of ["advocate-stop-circles", "advocate-stop-ranks"]) {
        if (map.getLayer(layer)) map.setLayoutProperty(layer, "visibility", showAdvocateStops ? "visible" : "none");
      }
      if (showAdvocateStops && advocateStops.features.length > 0) {
        const coordinates = advocateStops.features.map((feature) => feature.geometry.coordinates as [number, number]);
        const west = Math.min(...coordinates.map(([longitude]) => longitude));
        const east = Math.max(...coordinates.map(([longitude]) => longitude));
        const south = Math.min(...coordinates.map(([, latitude]) => latitude));
        const north = Math.max(...coordinates.map(([, latitude]) => latitude));
        const mobile = window.matchMedia("(max-width: 760px)").matches;
        const panel = document.querySelector(".panel")?.getBoundingClientRect();
        map.fitBounds([[west, south], [east, north]], {
          padding: {
            top: 90,
            right: 48,
            bottom: mobile && panel ? Math.round(panel.height + 100) : 100,
            left: mobile ? 48 : Math.round(Math.min((panel?.right || 408) + 56, window.innerWidth * 0.5)),
          },
          maxZoom: 11,
          duration: 450,
        });
      }
    };
    if (map.isStyleLoaded()) apply();
    else map.once("load", apply);
    return () => { map.off("load", apply); };
  }, [advocateStops, showAdvocateStops]);

  useEffect(() => {
    if (focusPoint && mapRef.current)
      mapRef.current.easeTo({
        center: [focusPoint[1], focusPoint[0]],
        zoom: 17,
        duration: 450,
      });
  }, [focusPoint]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const source = map.getSource("vta-stops") as
      | maplibregl.GeoJSONSource
      | undefined;
    source?.setData(stopFeatures(stops, destination?.stop_id));
  }, [stops]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    originMarker.current?.remove();
    originMarker.current = null;
    if (origin) {
      const element = document.createElement("div");
      element.className = "map-marker map-marker-origin";
      element.textContent = "A";
      element.setAttribute("aria-label", "Starting point");
      originMarker.current = new maplibregl.Marker({
        element,
        anchor: "center",
      })
        .setLngLat([origin[1], origin[0]])
        .addTo(map);
    }
  }, [origin]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    destinationMarker.current?.remove();
    destinationMarker.current = null;
    if (destination) {
      const element = document.createElement("div");
      element.className = "map-marker map-marker-destination";
      element.textContent = "B";
      element.setAttribute(
        "aria-label",
        `${route ? "Route arrival" : "Selected stop"}: ${destination.stop_name}`,
      );
      destinationMarker.current = new maplibregl.Marker({
        element,
        anchor: "center",
      })
        .setLngLat([destination.longitude, destination.latitude])
        .addTo(map);
      if (!route)
        map.easeTo({
          center: [destination.longitude, destination.latitude],
          zoom: Math.max(map.getZoom(), 15.5),
          duration: 450,
        });
    }
  }, [destination, route]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    reportMarker.current?.remove();
    reportMarker.current = null;
    if (reportPoint) {
      const element = document.createElement("div");
      element.className = "map-marker map-marker-report";
      element.textContent = "R";
      element.setAttribute("aria-label", "Selected community report location");
      reportMarker.current = new maplibregl.Marker({
        element,
        anchor: "center",
      })
        .setLngLat([reportPoint[1], reportPoint[0]])
        .addTo(map);
    }
  }, [reportPoint]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const updateRoute = () => {
      const source = map.getSource("route") as
        | maplibregl.GeoJSONSource
        | undefined;
      if (!source) return;
      source.setData(
        route || {
          type: "Feature",
          properties: {},
          geometry: { type: "LineString", coordinates: [] },
        },
      );
      if (container.current)
        container.current.dataset.routeState = route ? "current" : "clear";
      if (
        !route ||
        route.geometry.type !== "LineString" ||
        route.geometry.coordinates.length < 2
      )
        return;
      const coordinates = route.geometry.coordinates;
      const bounds = coordinates.reduce(
        (resultBounds, coordinate) =>
          resultBounds.extend(coordinate as [number, number]),
        new maplibregl.LngLatBounds(
          coordinates[0] as [number, number],
          coordinates[0] as [number, number],
        ),
      );
      const mobile = window.matchMedia("(max-width: 760px)").matches;
      const panel = document.querySelector(".panel")?.getBoundingClientRect();
      const bottomSheetHeight =
        mobile && panelExpanded ? panel?.height || 96 : mobile ? 96 : 40;
      map.fitBounds(bounds, {
        padding: {
          top: mobile ? 64 : 60,
          bottom: Math.max(40, Math.min(bottomSheetHeight + 24, window.innerHeight - 220)),
          left: mobile
            ? 32
            : (panel?.right || 408) + 40,
          right: mobile ? 32 : 64,
        },
        maxZoom: 17.5,
        duration: 500,
      });
    };
    if (map.getSource("route")) updateRoute();
    else map.once("load", updateRoute);
  }, [route, panelExpanded]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    map.getCanvas().style.cursor = selecting ? "crosshair" : "";
  }, [selecting]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const visibility = routeActive && !showStops ? "none" : "visible";
    const apply = () => {
      for (const id of ["stop-clusters", "stop-cluster-count", "vta-stops"])
        if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", visibility);
    };
    if (map.getLayer("vta-stops")) apply();
    else map.once("load", apply);
  }, [routeActive, showStops]);

  return (
    <div
      ref={container}
      className={`map ${selecting ? "map-selecting" : ""}`}
      role="application"
      aria-label="Map. Every map action is also available in the route planner. Select a stop marker to choose it as your destination."
    />
  );
}
