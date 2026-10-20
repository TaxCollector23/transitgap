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
};

const center: [number, number] = [-121.903, 37.3296];

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
        selected: stop.stop_id === selectedId,
      },
      geometry: { type: "Point", coordinates: [stop.longitude, stop.latitude] },
    })),
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
    id: "coverage-edge",
    type: "line",
    source: "coverage",
    paint: {
      "line-color": "#176b5b",
      "line-width": 1.5,
      "line-dasharray": [2, 2],
      "line-opacity": 0.65,
    },
  });
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
}: Props) {
  const container = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);
  const originMarker = useRef<Marker | null>(null);
  const destinationMarker = useRef<Marker | null>(null);
  const reportMarker = useRef<Marker | null>(null);
  const handlers = useRef({ onOrigin, onStop, onCandidate, selecting, stops });
  const latest = useRef({ route, destination, panelExpanded, coverage });
  const evidenceRef = useRef({ evidence, sidewalks });

  useEffect(() => {
    handlers.current = { onOrigin, onStop, onCandidate, selecting, stops };
    latest.current = { route, destination, panelExpanded, coverage };
    evidenceRef.current = { evidence, sidewalks };
  }, [
    onOrigin,
    onStop,
    onCandidate,
    selecting,
    stops,
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
      zoom: 14,
      minZoom: 8,
      maxZoom: 19,
      attributionControl: false,
      pixelRatio: Math.min(window.devicePixelRatio, 1.5),
      fadeDuration: 0,
      style: {
        version: 8,
        glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
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
          clusterRadius: 38,
          clusterMaxZoom: 15,
        });
        map.addLayer({
          id: "stop-clusters",
          type: "circle",
          source: "vta-stops",
          filter: ["has", "point_count"],
          paint: {
            "circle-color": "#176b5b",
            "circle-radius": [
              "step",
              ["get", "point_count"],
              15,
              8,
              18,
              18,
              21,
            ],
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": 2,
          },
        });
        map.addLayer({
          id: "stop-cluster-count",
          type: "symbol",
          source: "vta-stops",
          filter: ["has", "point_count"],
          layout: {
            "text-field": ["get", "point_count_abbreviated"],
            "text-font": ["Open Sans Semibold", "Arial Unicode MS Bold"],
            "text-size": 11,
          },
          paint: { "text-color": "#ffffff" },
        });
        map.addLayer({
          id: "vta-stops",
          type: "circle",
          source: "vta-stops",
          filter: ["!", ["has", "point_count"]],
          paint: {
            "circle-color": ["case", ["get", "selected"], "#d58c2e", "#176b5b"],
            "circle-radius": ["case", ["get", "selected"], 9, 6],
            "circle-stroke-color": "#ffffff",
            "circle-stroke-width": ["case", ["get", "selected"], 3, 2],
            "circle-opacity": 0.98,
          },
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
        map.addLayer({
          id: "route-outline",
          type: "line",
          source: "route",
          paint: {
            "line-color": "#ffffff",
            "line-width": 9,
            "line-opacity": 0.95,
          },
          layout: { "line-cap": "round", "line-join": "round" },
        });
        map.addLayer({
          id: "route-line",
          type: "line",
          source: "route",
          paint: {
            "line-color": "#176b5b",
            "line-width": 3,
            "line-opacity": 0.4,
          },
          layout: { "line-cap": "round", "line-join": "round" },
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
            "line-color": "#566672",
            "line-width": 9,
            "line-opacity": 0.55,
          },
        });
        map.addSource("route-segments", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });
        map.addLayer({
          id: "known-segments",
          type: "line",
          source: "route-segments",
          filter: ["!=", ["get", "status"], "unknown"],
          paint: {
            "line-color": [
              "match",
              ["get", "status"],
              "concern",
              "#b45622",
              "#176b5b",
            ],
            "line-width": 5,
          },
          layout: { "line-cap": "round", "line-join": "round" },
        });
        map.addLayer({
          id: "unknown-segments",
          type: "line",
          source: "route-segments",
          filter: ["==", ["get", "status"], "unknown"],
          paint: {
            "line-color": "#526779",
            "line-width": 5,
            "line-dasharray": [2, 1.6],
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
      }
    };

    map.on("load", () => {
      addLayers();
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
    if (coverage.bounds) {
      const { west, south, east, north } = coverage.bounds;
      const mobile = window.matchMedia("(max-width: 760px)").matches;
      const bottom =
        mobile && panelExpanded ? Math.min(window.innerHeight * 0.73, 680) : 78;
      map.fitBounds(
        [
          [west, south],
          [east, north],
        ],
        {
          padding: {
            top: 76,
            bottom: bottom + 24,
            left: mobile ? 24 : 450,
            right: 36,
          },
          maxZoom: 11,
          duration: 350,
        },
      );
    }
  }, [coverage]);

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
        `Selected stop: ${destination.stop_name}`,
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
        mobile && panelExpanded ? panel?.height || 96 : 96;
      map.fitBounds(bounds, {
        padding: {
          top: 76,
          bottom: Math.min(bottomSheetHeight + 20, window.innerHeight - 170),
          left: mobile
            ? 24
            : (document.querySelector(".panel")?.getBoundingClientRect()
                .right || 408) + 20,
          right: 42,
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

  return (
    <div
      ref={container}
      className={`map ${selecting ? "map-selecting" : ""}`}
      role="application"
      aria-label="Interactive map. Choose a starting point when map selection is active, or tap a VTA stop to choose your destination."
    />
  );
}
