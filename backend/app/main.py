from __future__ import annotations
import logging
import math
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException, Request
from fastapi import Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from shapely.geometry import Point, mapping
from .data_loader import (CENTER, COUNTY_RADIUS_M, COUNTY_REGION, DEFAULT_RADIUS_M,
                          DatasetError, data_dir, graph_cache_path, initialize, load_county_boundary)
from .models import Profile, RouteComparisonRequest, RouteRequest
from .routing import PROFILE_OBJECTIVES, calculate_route
from .data_sources.sanjose import load_sidewalks
from .groundtruth import GroundTruthIndex
from .observation_models import ObservationCreate
from .observations import (create_observation, database_durability,
                           initialize_observations, list_observations)
from .mcp_server import asgi_app as mcp_asgi_app, server as mcp_server

logger = logging.getLogger(__name__)
state = {"graph": None, "stops": [], "error": None, "radius_m": DEFAULT_RADIUS_M,
         "region": "diridon", "groundtruth": None, "groundtruth_error": None}
_report_rate: dict[str, deque[float]] = defaultdict(deque)

def _load() -> None:
    try:
        graph, stops = initialize()
        configured_region = os.getenv("TRANSITGAP_REGION", "").strip().lower()
        region = configured_region or (
            COUNTY_REGION if graph_cache_path(data_dir(), COUNTY_RADIUS_M, COUNTY_REGION).exists()
            else "diridon"
        )
        default_radius = COUNTY_RADIUS_M if region == COUNTY_REGION else DEFAULT_RADIUS_M
        radius = int(os.getenv("TRANSITGAP_RADIUS_M", default_radius))
        evidence_radius = DEFAULT_RADIUS_M
        try:
            city = load_sidewalks(radius_m=evidence_radius, allow_network=False)
        except Exception as exc:
            logger.exception("TransitGap municipal sidewalk snapshot could not be loaded")
            city = {"type": "FeatureCollection", "features": [], "metadata": {
                "source_name": "City of San Jose Sidewalks", "source_url": "https://geo.sanjoseca.gov/server/rest/services/OPN/OPN_OpenDataService/MapServer/185",
                "availability": "unavailable", "error": str(exc),
            }}
        try:
            index = GroundTruthIndex(graph, stops, city, radius_m=evidence_radius)
            gt_error = None
        except Exception as exc:
            logger.exception("TransitGap accessibility evidence index failed")
            index, gt_error = None, str(exc)
        try:
            initialize_observations()
        except Exception:
            logger.exception("TransitGap community report store initialization failed")
        state.update(graph=graph, stops=stops, error=None, radius_m=radius, region=region,
                     groundtruth=index, groundtruth_error=gt_error)
    except Exception as exc:
        logger.exception("TransitGap data initialization failed")
        state.update(graph=None, stops=[], error=str(exc))

@asynccontextmanager
async def lifespan(app: FastAPI):
    pool=ThreadPoolExecutor(max_workers=1)
    await __import__("asyncio").get_running_loop().run_in_executor(pool,_load)
    try:
        async with mcp_server.session_manager.run():
            yield
    finally:
        pool.shutdown(wait=False)

app=FastAPI(title="TransitGap API",version="0.1.0",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=os.getenv("CORS_ORIGINS","http://localhost:5173,http://127.0.0.1:5173").split(","),allow_credentials=False,allow_methods=["GET","POST","DELETE"],allow_headers=["*"],expose_headers=["Mcp-Session-Id"])

def _ready():
    if state["graph"] is None or not state["stops"]:
        raise HTTPException(status_code=503,detail={"message":"TransitGap data is not ready.","initialization_error":state["error"] or "Dataset initialization is still in progress."})

def _inside(lat:float,lon:float)->bool:
    if state.get("region") == COUNTY_REGION:
        try:
            return bool(load_county_boundary().covers(Point(lon, lat)))
        except DatasetError:
            return False
    lat0,lon0=CENTER; dlat=math.radians(lat-lat0); dlon=math.radians(lon-lon0)
    a=math.sin(dlat/2)**2+math.cos(math.radians(lat0))*math.cos(math.radians(lat))*math.sin(dlon/2)**2
    return 6371000*2*math.asin(math.sqrt(a)) <= state["radius_m"]

@app.get("/health")
def health():
    graph = state["graph"]
    return {
        "ready": graph is not None and bool(state["stops"]),
        "datasets": {
            "osm_walk_graph": "ready" if graph is not None else "unavailable",
            "vta_gtfs_stops": "ready" if state["stops"] else "unavailable",
        },
        "graph": ({"type": "directed_multigraph", "nodes": graph.number_of_nodes(),
                   "directed_edges": graph.number_of_edges()} if graph is not None else None),
        "vta_stop_count": len(state["stops"]),
        "community_report_storage": database_durability(),
        "groundtruth_ready": state["groundtruth"] is not None,
        "groundtruth_error": state["groundtruth_error"],
        "error": state["error"],
    }

@app.get("/coverage")
def coverage():
    if state.get("region") == COUNTY_REGION:
        boundary = load_county_boundary()
        west, south, east, north = boundary.bounds
        return {"region": "Santa Clara County", "center": {"latitude": 37.25, "longitude": -121.93},
                "radius_m": state["radius_m"], "bounds": {"west": west, "south": south, "east": east, "north": north},
                "boundary": mapping(boundary),
                "description": "Route coverage follows the U.S. Census Santa Clara County boundary. Walking paths come from OpenStreetMap; municipal sidewalk records currently come from the City of San Jose and do not cover every city.",
                "network_type": "OSM walk pedestrian graph", "accessibility_inventory_verified": False}
    return {"region":"Diridon Station area", "center":{"latitude":CENTER[0],"longitude":CENTER[1]},"radius_m":state["radius_m"],"description":"Supported query area around San Jose Diridon Station; actual mapped pedestrian paths may be incomplete.","network_type":"OSM walk pedestrian graph","accessibility_inventory_verified":False}


def _groundtruth():
    index = state.get("groundtruth")
    if index is None:
        raise HTTPException(503, detail={"message": "Accessibility comparison is unavailable.",
                                         "reason": state.get("groundtruth_error") or "Index is not ready."})
    return index


def _bbox(west: float | None, south: float | None, east: float | None, north: float | None):
    values = (west, south, east, north)
    if any(value is not None for value in values):
        if any(value is None for value in values):
            raise HTTPException(422, detail="Provide west, south, east, and north together.")
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise HTTPException(422, detail="Bounding box coordinates are invalid.")
        max_width, max_height = (1.2, 0.8) if state.get("region") == COUNTY_REGION else (0.2, 0.2)
        if east - west > max_width or north - south > max_height:
            raise HTTPException(422, detail="Bounding box is larger than the supported map area.")
    return values


@app.get("/data-sources")
def data_sources():
    return _groundtruth().source_status()


@app.get("/accessibility/gaps")
def accessibility_gaps(west: float | None = None, south: float | None = None,
                       east: float | None = None, north: float | None = None,
                       limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    _bbox(west, south, east, north)
    return _groundtruth().get_gaps(west=west, south=south, east=east, north=north,
                                  limit=limit, offset=offset)


@app.get("/accessibility/gaps/{candidate_id}")
def accessibility_gap(candidate_id: str):
    candidate = _groundtruth().get_candidate(candidate_id)
    if candidate is None:
        raise HTTPException(404, detail="Accessibility candidate not found.")
    return candidate


@app.get("/accessibility/priorities")
def accessibility_priorities(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    return _groundtruth().get_priorities(limit=limit, offset=offset)


@app.get("/accessibility/municipal-sidewalks")
def municipal_sidewalks(west: float | None = None, south: float | None = None,
                         east: float | None = None, north: float | None = None,
                         limit: int = Query(300, ge=1, le=1000), offset: int = Query(0, ge=0)):
    _bbox(west, south, east, north)
    return _groundtruth().municipal_features(west, south, east, north, limit, offset)


@app.get("/accessibility/observations")
def observations(west: float | None = None, south: float | None = None,
                 east: float | None = None, north: float | None = None,
                 limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    _bbox(west, south, east, north)
    try:
        return list_observations(west=west, south=south, east=east, north=north,
                                 limit=limit, offset=offset)
    except Exception as exc:
        logger.exception("Community report listing unavailable")
        raise HTTPException(503, detail="Community report storage is unavailable.") from exc


@app.post("/accessibility/observations", status_code=201)
def submit_observation(payload: ObservationCreate, request: Request):
    if not _inside(payload.latitude, payload.longitude):
        raise HTTPException(422, detail=f"Reports must be within the supported {state['region'].replace('_', ' ')} area.")
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    attempts = _report_rate[client]
    while attempts and now - attempts[0] >= 60:
        attempts.popleft()
    if len(attempts) >= 5:
        raise HTTPException(429, detail="Please wait before submitting another report.")
    attempts.append(now)
    related = _groundtruth().find_candidate_for_point(payload.latitude, payload.longitude)
    try:
        return create_observation(latitude=payload.latitude, longitude=payload.longitude,
                                  category=payload.category.value, description=payload.description,
                                  related_feature_id=related)
    except Exception as exc:
        logger.exception("Community report submission failed")
        raise HTTPException(503, detail="Community report storage is unavailable.") from exc

@app.get("/stops")
def stops():
    _ready()
    return {"stops":[{k:v for k,v in stop.items() if k!="graph_node" and k!="connector_distance_m"} for stop in state["stops"]],"count":len(state["stops"])}

@app.post("/route")
def route(payload:RouteRequest):
    graph, stop = _route_inputs(payload.origin_latitude, payload.origin_longitude, payload.destination_stop_id)
    try:
        result = calculate_route(graph, (payload.origin_latitude, payload.origin_longitude),
                                 stop["graph_node"], payload.algorithm, payload.profile, stop)
        index = state.get("groundtruth")
        result["groundtruth_evidence"] = index.route_evidence(result["geometry"]) if index else {
            "status": "unavailable", "nearby_feature_count": 0, "features": [],
            "message": "Municipal sidewalk comparison is unavailable."}
        return result
    except LookupError as exc:
        logger.info("Route unavailable for requested destination and profile %s", payload.profile.value)
        raise HTTPException(422, detail=str(exc)) from exc
    except ValueError as exc:
        logger.warning("Routing rejected invalid graph cost or configuration: %s", exc)
        raise HTTPException(422, detail=str(exc)) from exc


def _route_inputs(latitude: float, longitude: float, stop_id: str):
    _ready()
    if not _inside(latitude, longitude):
        area = "Santa Clara County" if state.get("region") == COUNTY_REGION else f"the {state['radius_m']} m Diridon Station study area"
        raise HTTPException(422, detail=f"Starting point is outside the supported area ({area}).")
    stop = next((candidate for candidate in state["stops"] if candidate["stop_id"] == stop_id), None)
    if stop is None:
        raise HTTPException(404, detail="The selected destination is not in the loaded VTA stop dataset.")
    return state["graph"], stop


@app.post("/route/compare")
def compare_routes(payload: RouteComparisonRequest):
    """Run all supported routing objectives against the same loaded graph."""
    graph, stop = _route_inputs(payload.origin_latitude, payload.origin_longitude, payload.destination_stop_id)
    results = []
    for profile in (Profile.standard, Profile.avoid_mapped_stairs, Profile.prefer_documented_paths):
        try:
            result = calculate_route(graph, (payload.origin_latitude, payload.origin_longitude),
                                     stop["graph_node"], payload.algorithm, profile, stop)
            index = state.get("groundtruth")
            result["groundtruth_evidence"] = index.route_evidence(result["geometry"]) if index else {
                "status": "unavailable", "nearby_feature_count": 0, "features": [],
                "message": "Municipal sidewalk comparison is unavailable."}
            results.append({"profile": profile.value, "objective": PROFILE_OBJECTIVES[profile],
                            "available": True, "route": result, "error": None})
        except (LookupError, ValueError) as exc:
            results.append({"profile": profile.value, "objective": PROFILE_OBJECTIVES[profile],
                            "available": False, "route": None, "error": str(exc)})
    return {
        "algorithm": payload.algorithm.value,
        "origin": {"latitude": payload.origin_latitude, "longitude": payload.origin_longitude},
        "destination": {key: stop[key] for key in ("stop_id", "stop_name", "latitude", "longitude")},
        "results": results,
    }

# Vercel builds the React app before importing this ASGI app. In local development,
# Vite serves the frontend separately and this mount is available after a production build.
_frontend = Path(__file__).resolve().parents[2] / "frontend" / "dist"
# Register the exact endpoint before the static catch-all. A Mount at /mcp
# only matches /mcp/, allowing StaticFiles to intercept slashless MCP requests.
app.router.routes.extend(mcp_asgi_app.routes)
if _frontend.exists():
    @app.get("/app", include_in_schema=False)
    @app.get("/app/{app_path:path}", include_in_schema=False)
    def app_shell(app_path: str = ""):
        """Serve the SPA entry point for direct navigation and refreshed app links."""
        return FileResponse(_frontend / "index.html")

    app.mount("/", StaticFiles(directory=_frontend, html=True), name="frontend")
