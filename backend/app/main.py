from __future__ import annotations
import json
import asyncio
import hmac
import hashlib
import uuid
from datetime import datetime, timezone, timedelta
import logging
import math
import os
import time
from collections import defaultdict, deque
from contextvars import ContextVar
from itertools import count
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException, Request
from fastapi import Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse
from pathlib import Path
from typing import Literal
from shapely.geometry import Point, mapping
from .data_loader import (
    CENTER,
    COUNTY_RADIUS_M,
    COUNTY_REGION,
    DEFAULT_RADIUS_M,
    DatasetError,
    data_dir,
    graph_cache_path,
    initialize,
    load_county_boundary,
)
from .models import Algorithm, Profile, RouteComparisonRequest, RouteRequest
from .gaps import GapIndex
from .transit import TransitSchedule, modes as _modes
from .prepared_frontend import public_stop as _public_stop
from .transit_agencies import AGENCIES, load_agency_stops
from .geospatial import nearest_graph_node
from .profiles import SPEED_MPS, configuration
from .routing import PROFILE_OBJECTIVES, calculate_route as base_calculate_route, _edge_coords
from .data_sources.sanjose import load_sidewalks
from .groundtruth_cache import load_groundtruth
from .public_api_snapshots import (
    DATA_SOURCES_FILE,
    PRIORITIES_FILE,
    REACHABILITY_STOPS_FILE,
    page_priorities,
    read_public_api_snapshot,
    with_agency_sources,
)
from .observation_models import ObservationCreate, ObservationReview
from .observations import (
    create_observation,
    database_durability,
    initialize_observations,
    list_observations,
    observation_detail,
    review_observation,
    active_routing_effects,
    consume_report_quota,
)
from .reachability import (
    MAX_MINUTES as REACHABILITY_MAX_MINUTES,
    MAX_SAMPLE_SIZE as REACHABILITY_MAX_SAMPLE,
    build_reachability_index,
    pilot_gtfs_stops,
)
from .mcp_server import asgi_app as mcp_asgi_app, server as mcp_server

logger = logging.getLogger(__name__)
PROCESS_INSTANCE_ID = uuid.uuid4().hex[:12]
PROCESS_STARTED_AT = datetime.now(timezone.utc)
PROCESS_STARTED_MONOTONIC = time.perf_counter()
PROCESS_REQUEST_SEQUENCE = count(1)
ACTIVE_REQUEST_CONTEXT: ContextVar[dict | None] = ContextVar("transitgap_request_context", default=None)
state = {
    "graph": None,
    "stops": [],
    "transit_stops": [],
    "agency_schedules": {},
    "transit_sources": {},
    "error": None,
    "radius_m": DEFAULT_RADIUS_M,
    "region": "diridon",
    "groundtruth": None,
    "groundtruth_error": None,
    "reachability_index": None,
}
_report_rate: dict[str, deque[float]] = defaultdict(deque)

def _runtime_event(event: str, **fields) -> None:
    """Emit content-free, structured timing data correlated to a worker."""
    try:
        print(json.dumps({"event": event, "instance_id": PROCESS_INSTANCE_ID,
                          "deployment_id": os.getenv("VERCEL_DEPLOYMENT_ID"), **fields},
                         separators=(",", ":"), sort_keys=True), flush=True)
    except OSError:
        # Diagnostics must not turn a healthy route or loader into a failure.
        pass






STEP_FREE_PROFILES = {Profile.wheelchair, Profile.avoid_mapped_stairs, Profile.stroller}


def _arrival_targets(stop: dict, profile: Profile) -> list[tuple[str, dict, dict]]:
    """Where a walking route should end for a stop.

    A station entrance recorded in GTFS is a real, published access point, so
    routes end there instead of drawing an unmapped line to a platform
    coordinate. Step-free profiles use entrances the feed marks accessible
    when it records that; entrances marked inaccessible are never used for
    them. Stops without recorded entrances route to the stop itself."""
    entrances = [e for e in stop.get("entrances") or [] if e.get("graph_node") is not None]
    if profile in STEP_FREE_PROFILES:
        recorded_entrances = entrances
        accessible = [e for e in entrances if e.get("wheelchair_boarding") == 1]
        entrances = accessible or [e for e in entrances if e.get("wheelchair_boarding") != 2]
        if recorded_entrances and not entrances:
            raise LookupError("The agency marks every recorded station entrance as not step-free. TransitGap cannot infer another accessible entrance; choose another destination or confirm access with the agency.")
    label = stop.get("station_name") or stop["stop_name"]
    targets = [
        (e["graph_node"],
         {**stop, "stop_name": f"{label}, {e['name']}", "latitude": e["latitude"], "longitude": e["longitude"]},
         {"type": "entrance", "entrance_id": e["entrance_id"], "name": e["name"],
          "latitude": e["latitude"], "longitude": e["longitude"],
          "wheelchair_boarding": e.get("wheelchair_boarding", 0),
          "note": "Route ends at an entrance recorded in the agency's GTFS feed. The path inside the station to the platform is not part of this route."})
        for e in entrances
    ]
    if targets:
        return targets
    platform = stop
    if stop.get("station_name") and stop.get("platform_name"):
        platform = {**stop, "stop_name": f"{stop['station_name']}, {stop['platform_name']}"}
    return [(stop["graph_node"], platform, {"type": "stop", "note": None})]


def _load() -> None:
    started = time.perf_counter()
    cpu_started=time.process_time()
    phase_wall,phase_cpu=started,cpu_started
    timings={}
    database_timings={}
    phase_name="walking_network"
    _runtime_event("initialization_started", stage=phase_name,
                   process_started_at=PROCESS_STARTED_AT.isoformat())
    def phase(name):
        nonlocal phase_wall,phase_cpu,phase_name
        wall,cpu=time.perf_counter(),time.process_time()
        timings[phase_name]={"wall_seconds":round(wall-phase_wall,3),"cpu_seconds":round(cpu-phase_cpu,3)}
        _runtime_event("initialization_stage_complete", stage=phase_name,
                       next_stage=name, **timings[phase_name])
        phase_wall,phase_cpu,phase_name=wall,cpu,name
        state["initialization_phase"]=name
    try:
        state.update(initialization_phase="walking_network", error=None)
        graph, stops = initialize()
        phase("rail_stops_and_schedules")
        configured_region = os.getenv("TRANSITGAP_REGION", "").strip().lower()
        region = configured_region or (
            COUNTY_REGION
            if graph_cache_path(data_dir(), COUNTY_RADIUS_M, COUNTY_REGION).exists()
            else "diridon"
        )
        default_radius = (
            COUNTY_RADIUS_M if region == COUNTY_REGION else DEFAULT_RADIUS_M
        )
        radius = int(os.getenv("TRANSITGAP_RADIUS_M", default_radius))
        if region == COUNTY_REGION:
            rail_stops, transit_sources = load_agency_stops(graph, data_dir(), region, radius)
        else:
            rail_stops, transit_sources = [], {}
        agency_schedules = {}
        for agency_id, config in AGENCIES.items():
            agency_stop_ids = [stop["source_stop_id"] for stop in rail_stops if stop["agency"] == agency_id]
            if agency_stop_ids:
                try:
                    agency_schedules[agency_id] = TransitSchedule(
                        data_dir() / config["file"], agency_stop_ids,
                        data_dir() / f"schedule-{agency_id}-v2.json.gz",
                    )
                except Exception:
                    logger.exception("%s schedule unavailable", config["name"])
        for stop in rail_stops:
            agency_schedule = agency_schedules.get(stop["agency"])
            stop["modes"] = _modes(agency_schedule.route_types(stop["source_stop_id"])) if agency_schedule else []
            stop["routes_served"] = agency_schedule.routes_served(stop["source_stop_id"]) if agency_schedule else []
        phase("spatial_index")
        # Prepare the spherical index once, rather than in the first route.
        nearest_graph_node(graph, CENTER[0], CENTER[1])
        phase("prepared_gap_cache")
        gaps = GapIndex(graph, stops, data_dir())
        phase("vta_schedule")
        try:
            schedule = TransitSchedule(
                data_dir() / "gtfs_vta.zip", [s["stop_id"] for s in stops]
            )
        except Exception:
            logger.exception("GTFS schedule unavailable")
            schedule = None
        for stop in stops:
            stop["modes"] = _modes(schedule.route_types(stop["stop_id"])) if schedule else []
            stop["routes_served"] = schedule.routes_served(stop["stop_id"]) if schedule else []
        phase("municipal_snapshot")
        evidence_radius = DEFAULT_RADIUS_M
        try:
            city = load_sidewalks(radius_m=evidence_radius, allow_network=False)
        except Exception as exc:
            logger.exception(
                "TransitGap municipal sidewalk snapshot could not be loaded"
            )
            city = {
                "type": "FeatureCollection",
                "features": [],
                "metadata": {
                    "source_name": "City of San Jose Sidewalks",
                    "source_url": "https://geo.sanjoseca.gov/server/rest/services/OPN/OPN_OpenDataService/MapServer/185",
                    "availability": "unavailable",
                    "error": str(exc),
                },
            }
        phase("evidence_index")
        try:
            index = load_groundtruth(graph, stops, city, data_dir(), gaps.signature)
            gt_error = None
        except Exception as exc:
            logger.exception("TransitGap accessibility evidence index failed")
            index, gt_error = None, str(exc)
        try:
            phase("report_storage")
            database_started, database_cpu_started = time.perf_counter(), time.process_time()
            initialize_observations(timings=database_timings)
            observations_ready = True
            _runtime_event("database_initialization_complete", **database_timings,
                           total_wall_seconds=round(time.perf_counter()-database_started,4),
                           total_process_cpu_seconds=round(time.process_time()-database_cpu_started,4))
        except Exception as exc:
            observations_ready = False
            _runtime_event("database_initialization_failed", error_type=type(exc).__name__,
                           total_wall_seconds=round(time.perf_counter()-database_started,4),
                           total_process_cpu_seconds=round(time.process_time()-database_cpu_started,4))
            logger.exception("TransitGap community report store initialization failed")
        phase("ready")
        state.update(
            graph=graph,
            stops=stops,
            transit_stops=[*stops, *rail_stops],
            agency_schedules=agency_schedules,
            transit_sources=transit_sources,
            error=None,
            radius_m=radius,
            region=region,
            groundtruth=index,
            groundtruth_error=gt_error,
            reachability_index=None,
            gaps=gaps,
            schedule=schedule,
            observations_ready=observations_ready,
            initialization_seconds=round(time.perf_counter() - started, 3),
            initialization_phase="ready",
            initialization_cpu_seconds=round(time.process_time()-cpu_started,3),
            initialization_timings=timings,
            database_initialization_timings=database_timings,
            schedule_cache_hits={"VTA":getattr(schedule,"cache_hit",None),**{k:getattr(v,"cache_hit",None) for k,v in agency_schedules.items()}},
        )
        _runtime_event("initialization_ready", wall_seconds=state["initialization_seconds"],
                       cpu_seconds=state["initialization_cpu_seconds"],
                       rss_mib=_process_memory().get("rss_mib"), timings=timings,
                       schedule_cache_hits=state["schedule_cache_hits"])
    except Exception as exc:
        _runtime_event("initialization_failed", stage=phase_name,
                       wall_seconds=round(time.perf_counter()-started,3),
                       cpu_seconds=round(time.process_time()-cpu_started,3),
                       error_type=type(exc).__name__)
        logger.exception("TransitGap data initialization failed")
        state.update(graph=None, stops=[], error=str(exc), initialization_phase="failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("VERCEL"):
        os.environ.setdefault("TRANSITGAP_CACHE_ONLY", "1")
    pool = ThreadPoolExecutor(max_workers=1)
    initialization = __import__("asyncio").get_running_loop().run_in_executor(pool, _load)
    app.state.initialization = initialization
    if os.getenv("TRANSITGAP_ASYNC_STARTUP", "1" if os.getenv("VERCEL") else "0") != "1":
        await initialization
    try:
        async with mcp_server.session_manager.run():
            yield
    finally:
        pool.shutdown(wait=False)


app = FastAPI(title="TransitGap API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "CORS_ORIGINS", "https://transitgap.vercel.app,http://localhost:5173,http://127.0.0.1:5173"
    ).split(","),
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
    expose_headers=["Mcp-Session-Id", "X-TransitGap-Instance", "X-TransitGap-Request-Number", "X-TransitGap-Request-ID", "X-TransitGap-Init-Phase"],
)


@app.middleware("http")
async def instance_telemetry(request: Request, call_next):
    sequence = next(PROCESS_REQUEST_SEQUENCE)
    request_id = request.headers.get("x-vercel-id") if os.getenv("VERCEL") else None
    request_id = request_id or uuid.uuid4().hex[:16]
    started, cpu_started = time.perf_counter(), time.process_time()
    context_token = ACTIVE_REQUEST_CONTEXT.set({"request_id": request_id, "request_number": sequence})
    try:
        response = await call_next(request)
    except Exception as exc:
        _runtime_event("request_failed", request_id=request_id, request_number=sequence,
                       method=request.method, path=request.url.path,
                       wall_seconds=round(time.perf_counter()-started,4),
                       process_cpu_seconds=round(time.process_time()-cpu_started,4),
                       initialization_phase=state.get("initialization_phase", "starting"),
                       error_type=type(exc).__name__)
        raise
    finally:
        ACTIVE_REQUEST_CONTEXT.reset(context_token)
    wall = round(time.perf_counter()-started, 4)
    process_cpu = round(time.process_time()-cpu_started, 4)
    phase = state.get("initialization_phase", "starting")
    response.headers["X-TransitGap-Instance"] = PROCESS_INSTANCE_ID
    response.headers["X-TransitGap-Request-Number"] = str(sequence)
    response.headers["X-TransitGap-Request-ID"] = request_id
    response.headers["X-TransitGap-Init-Phase"] = str(phase)
    if request.url.path in {"/health", "/health/live", "/routing/initialize", "/route"}:
        _runtime_event("request_complete", request_id=request_id, request_number=sequence,
                       method=request.method, path=request.url.path,
                       status=response.status_code, wall_seconds=wall,
                       process_cpu_seconds=process_cpu, initialization_phase=phase,
                       ready=state.get("graph") is not None)
    return response


def _ready():
    if state["graph"] is None or not state["stops"]:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "TransitGap data is not ready.",
                "initialization_error": state["error"]
                or "Dataset initialization is still in progress.",
            },
        )


def _inside(lat: float, lon: float) -> bool:
    if state.get("region") == COUNTY_REGION:
        try:
            return bool(load_county_boundary().covers(Point(lon, lat)))
        except DatasetError:
            return False
    lat0, lon0 = CENTER
    dlat = math.radians(lat - lat0)
    dlon = math.radians(lon - lon0)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat0))
        * math.cos(math.radians(lat))
        * math.sin(dlon / 2) ** 2
    )
    return 6371000 * 2 * math.asin(math.sqrt(a)) <= state["radius_m"]


def _reporting_enabled():
    durability=database_durability()
    return bool(state.get("observations_ready",False) and durability in {"filesystem-persistent","postgresql"}
                and (durability!="postgresql" or len(os.getenv("TRANSITGAP_REPORT_RATE_SECRET",""))>=32))


def _process_memory():
    import sys
    peak=current=None
    try:
        import resource
        peak=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if sys.platform=="darwin" else 1024),2)
    except ImportError:
        pass
    try:
        resident=int(Path('/proc/self/statm').read_text().split()[1])
        current=round(resident*os.sysconf('SC_PAGE_SIZE')/1024**2,2)
    except (OSError,ValueError,IndexError):
        pass
    return {"rss_mib":current,"peak_rss_mib":peak}


@app.get("/health")
def health():
    graph = state["graph"]
    return {
        "runtime": {"instance_id": PROCESS_INSTANCE_ID,
                    "process_started_at": PROCESS_STARTED_AT.isoformat(),
                    "uptime_seconds": round(time.perf_counter()-PROCESS_STARTED_MONOTONIC, 3)},
        "ready": graph is not None and bool(state["stops"]),
        "build_sha": os.getenv("TRANSITGAP_BUILD_SHA") or os.getenv("VERCEL_GIT_COMMIT_SHA"),
        "datasets": {
            "osm_walk_graph": "ready" if graph is not None else "unavailable",
            "vta_gtfs_stops": "ready" if state["stops"] else "unavailable",
            "caltrain_gtfs_stops": "ready" if "caltrain" in state.get("transit_sources", {}) else "unavailable",
            "bart_gtfs_stops": "ready" if "bart" in state.get("transit_sources", {}) else "unavailable",
        },
        "graph": (
            {
                "type": "directed_multigraph",
                "nodes": graph.number_of_nodes(),
                "directed_edges": graph.number_of_edges(),
            }
            if graph is not None
            else None
        ),
        "vta_stop_count": len(state["stops"]),
        "transit_stop_counts": {
            "VTA": len(state["stops"]),
            **{source["name"]: source["stop_count"] for source in state.get("transit_sources", {}).values()},
        },
        "community_report_storage": database_durability(),
        "reports_enabled": _reporting_enabled(),
        "gap_stops_evaluated": len(state["gaps"].cache) if state.get("gaps") else 0,
        "schedule_ready": state.get("schedule") is not None,
        "data_freshness": (
            state["schedule"].feed_info if state.get("schedule") else None
        ),
        "groundtruth_ready": state["groundtruth"] is not None,
        "groundtruth_error": state["groundtruth_error"],
        "error": state["error"],
        "initialization_seconds": state.get("initialization_seconds"),
        "initialization_cpu_seconds": state.get("initialization_cpu_seconds"),
        "initialization_timings": state.get("initialization_timings"),
        "database_initialization_timings": state.get("database_initialization_timings"),
        "schedule_cache_hits": state.get("schedule_cache_hits"),
        "process_memory": _process_memory(),
    }


@app.get("/coverage")
def coverage():
    if state.get("region") == COUNTY_REGION:
        boundary = load_county_boundary()
        west, south, east, north = boundary.bounds
        return {
            "region": "Santa Clara County",
            "center": {"latitude": 37.25, "longitude": -121.93},
            "radius_m": state["radius_m"],
            "bounds": {"west": west, "south": south, "east": east, "north": north},
            "boundary": mapping(boundary),
            "description": "Route coverage follows the U.S. Census Santa Clara County boundary. Walking paths come from OpenStreetMap; municipal sidewalk records currently come from the City of San Jose and do not cover every city.",
            "network_type": "OSM walk pedestrian graph",
            "accessibility_inventory_verified": False,
        }
    return {
        "region": "Diridon Station area",
        "center": {"latitude": CENTER[0], "longitude": CENTER[1]},
        "radius_m": state["radius_m"],
        "description": "Supported query area around San Jose Diridon Station; actual mapped pedestrian paths may be incomplete.",
        "network_type": "OSM walk pedestrian graph",
        "accessibility_inventory_verified": False,
    }


def _groundtruth():
    index = state.get("groundtruth")
    if index is None:
        raise HTTPException(
            503,
            detail={
                "message": "Accessibility comparison is unavailable.",
                "reason": state.get("groundtruth_error") or "Index is not ready.",
            },
        )
    return index


def _bbox(
    west: float | None, south: float | None, east: float | None, north: float | None
):
    values = (west, south, east, north)
    if any(value is not None for value in values):
        if any(value is None for value in values):
            raise HTTPException(
                422, detail="Provide west, south, east, and north together."
            )
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise HTTPException(422, detail="Bounding box coordinates are invalid.")
        max_width, max_height = (
            (1.2, 0.8) if state.get("region") == COUNTY_REGION else (0.2, 0.2)
        )
        if east - west > max_width or north - south > max_height:
            raise HTTPException(
                422, detail="Bounding box is larger than the supported map area."
            )
    return values


@app.get("/data-sources")
def data_sources():
    snapshot = read_public_api_snapshot(data_dir(), DATA_SOURCES_FILE)
    if snapshot is not None:
        return snapshot
    return with_agency_sources(
        _groundtruth().source_status(), state.get("transit_sources", {})
    )


@app.get("/accessibility/gaps")
def accessibility_gaps(
    west: float | None = None,
    south: float | None = None,
    east: float | None = None,
    north: float | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    _bbox(west, south, east, north)
    return _groundtruth().get_gaps(
        west=west, south=south, east=east, north=north, limit=limit, offset=offset
    )


@app.get("/accessibility/gaps/{candidate_id}")
def accessibility_gap(candidate_id: str):
    candidate = _groundtruth().get_candidate(candidate_id)
    if candidate is None:
        raise HTTPException(404, detail="Accessibility candidate not found.")
    return candidate


@app.get("/accessibility/priorities")
def accessibility_priorities(
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)
):
    snapshot = read_public_api_snapshot(data_dir(), PRIORITIES_FILE, compressed=True)
    if snapshot is not None:
        return page_priorities(snapshot, limit=limit, offset=offset)
    return _groundtruth().get_priorities(limit=limit, offset=offset)


def _reachability_study():
    _ready()
    if state.get("reachability_index") is None:
        graph_path = graph_cache_path(data_dir(), state["radius_m"], state["region"])
        metadata_path = graph_path.with_suffix(".metadata.json")
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            metadata = {"source": "OpenStreetMap", "graph_modified_at": None, "manifest_generated_at": None}
        schedule = state.get("schedule")
        state["reachability_index"] = build_reachability_index(
            state["graph"], pilot_gtfs_stops(state["graph"], data_dir() / "gtfs_vta.zip"), metadata,
            schedule.feed_info if schedule else [],
        )
    return state["reachability_index"]


@app.get("/accessibility/reachability/stops")
def reachability_stops():
    """Actual VTA stops connected to the bounded Diridon pilot graph."""
    snapshot = read_public_api_snapshot(data_dir(), REACHABILITY_STOPS_FILE)
    if snapshot is not None:
        return snapshot
    try:
        index = _reachability_study()
    except Exception as exc:
        logger.exception("Diridon reachability data is unavailable")
        raise HTTPException(503, detail="The Diridon OSM and VTA pilot data could not be loaded.") from exc
    return {
        "study_area": {"name": "Diridon Station pilot", "radius_m": 1500},
        "stop_count": len(index.stops),
        "stops": index.stop_list(),
        "source": "Actual VTA GTFS stops in the 1,500 m Diridon view of the county walking graph; nearest-node matches are not field checked.",
    }


@app.get("/accessibility/reachability/{stop_id}")
def stop_reachability(
    stop_id: str,
    profile: Profile = Profile.wheelchair,
    minutes: int = Query(10, ge=1, le=REACHABILITY_MAX_MINUTES),
    sample_size: int = Query(150, ge=20, le=REACHABILITY_MAX_SAMPLE),
    documentation_policy: Literal["profile_required", "width_optional_sensitivity"] = "profile_required",
):
    """Compare source-documented and permissive reach toward one real pilot stop."""
    try:
        return _reachability_study().analyze(stop_id, profile, minutes, sample_size, documentation_policy)
    except KeyError as exc:
        raise HTTPException(404, detail="VTA stop is outside the Diridon reachability pilot.") from exc
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Bounded stop reachability analysis failed")
        raise HTTPException(503, detail="The bounded reachability analysis is unavailable.") from exc


@app.get("/accessibility/municipal-sidewalks")
def municipal_sidewalks(
    west: float | None = None,
    south: float | None = None,
    east: float | None = None,
    north: float | None = None,
    limit: int = Query(300, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    _bbox(west, south, east, north)
    return _groundtruth().municipal_features(west, south, east, north, limit, offset)


@app.get("/accessibility/observations")
def observations(
    west: float | None = None,
    south: float | None = None,
    east: float | None = None,
    north: float | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    _bbox(west, south, east, north)
    try:
        return list_observations(
            west=west, south=south, east=east, north=north, limit=limit, offset=offset
        )
    except Exception as exc:
        logger.exception("Community report listing unavailable")
        raise HTTPException(
            503, detail="Community report storage is unavailable."
        ) from exc


@app.post("/accessibility/observations", status_code=201)
def submit_observation(payload: ObservationCreate, request: Request):
    if not _reporting_enabled():
        raise HTTPException(
            503,
            detail="Public reporting is paused until durable storage is connected. Your report has not been saved.",
        )
    if not _inside(payload.latitude, payload.longitude):
        raise HTTPException(
            422,
            detail=f"Reports must be within the supported {state['region'].replace('_', ' ')} area.",
        )
    client = request.client.host if request.client else "unknown"
    if os.getenv("VERCEL"):
        client = request.headers.get("x-vercel-forwarded-for", client)
    secret = os.getenv("TRANSITGAP_REPORT_RATE_SECRET", "")
    if database_durability() == "postgresql":
        if len(secret) < 32:
            raise HTTPException(503, detail="Report spam protection is not configured. Your report has not been saved.")
        fingerprint = hmac.new(secret.encode(), client.encode(), hashlib.sha256).hexdigest()
        try:
            allowed = consume_report_quota(fingerprint)
        except Exception as exc:
            raise HTTPException(503, detail="Community report storage is unavailable. Your report has not been saved.") from exc
        if not allowed:
            raise HTTPException(429, detail="Please wait before submitting another report.", headers={"Retry-After":"60"})
    submission_key = request.headers.get("idempotency-key")
    if submission_key:
        try:
            submission_key = str(uuid.UUID(submission_key))
        except ValueError as exc:
            raise HTTPException(422, detail="Invalid submission key.") from exc
    if database_durability() != "postgresql":
        now = time.monotonic()
        if len(_report_rate) >= 10000:
            for key in list(_report_rate):
                if not _report_rate[key] or now-_report_rate[key][-1]>=60:
                    _report_rate.pop(key,None)
            if len(_report_rate)>=10000:
                raise HTTPException(429,detail="Please wait before submitting another report.")
        attempts = _report_rate[client]
        while attempts and now - attempts[0] >= 60:
            attempts.popleft()
        if len(attempts) >= 5:
            raise HTTPException(429, detail="Please wait before submitting another report.")
        attempts.append(now)
    related = state["groundtruth"].find_candidate_for_point(payload.latitude, payload.longitude) if state.get("groundtruth") else None
    try:
        return create_observation(
            latitude=payload.latitude,
            longitude=payload.longitude,
            category=payload.category.value,
            description=payload.description,
            related_feature_id=related,
            submission_key=submission_key,
        )
    except ValueError as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Community report submission failed")
        raise HTTPException(
            503, detail="Community report storage is unavailable."
        ) from exc


@app.get("/health/live")
def liveness():
    return {"alive":True,"ready":state["graph"] is not None,"reports_ready":state.get("observations_ready",False),"error":state.get("error"),"phase":state.get("initialization_phase","starting"),"instance_id":PROCESS_INSTANCE_ID}


INITIALIZATION_REQUEST_SECONDS = 45


@app.post("/routing/initialize")
async def initialize_routing():
    """Keep compute active during a bounded serverless warmup request.

    A thread alone can be suspended after the last response. Await long enough
    for the measured county initialization to finish in the same invocation;
    shielding preserves it if the client's bounded request eventually expires.
    Other requests, CDN stop search and the map remain independent.
    """
    initialization = getattr(app.state, "initialization", None)
    if initialization is not None and not initialization.done():
        try:
            await asyncio.wait_for(asyncio.shield(initialization), INITIALIZATION_REQUEST_SECONDS)
        except TimeoutError:
            pass
    return liveness()


@app.get("/mobility-profiles")
def mobility_profiles():
    return {"assumptions":configuration(),"note":"Model assumptions, not legal compliance or a safety certification. Missing values remain unknown."}


@app.get("/accessibility/observations/{identity}")
def report_detail(identity: str):
    try:return observation_detail(identity)
    except LookupError as exc:raise HTTPException(404,detail=str(exc)) from exc
    except Exception as exc:raise HTTPException(503,detail="Community report storage is unavailable.") from exc


def _require_reviewer(request: Request):
    token=os.getenv("TRANSITGAP_MODERATION_TOKEN","")
    if len(token)<32:raise HTTPException(503,detail="Moderation is not configured.")
    if not hmac.compare_digest(request.headers.get("authorization",""),"Bearer "+token):raise HTTPException(403,detail="Reviewer authorization required.")


@app.get("/admin/observations")
def review_queue(request: Request, limit: int = Query(100,ge=1,le=500), offset: int = Query(0,ge=0)):
    _require_reviewer(request)
    try:
        return list_observations(limit=limit,offset=offset,include_inactive=True)
    except Exception as exc:
        raise HTTPException(503,detail="Community report storage is unavailable.") from exc


@app.post("/accessibility/observations/{identity}/review")
def moderate_report(identity: str, payload: ObservationReview, request: Request):
    _require_reviewer(request)
    reference=payload.edge_reference
    expiry=payload.effective_until.astimezone(timezone.utc) if payload.effective_until else None
    if payload.effective_until and payload.effective_until.tzinfo is None:raise HTTPException(422,detail="Review expiry must include a timezone.")
    profiles={"standard","wheelchair","stroller","low_vision","prefer_documented_paths"}
    if not set(payload.affected_profiles)<=profiles:raise HTTPException(422,detail="Unsupported affected mobility profile.")
    if payload.routing_effect!="none":
        if payload.status.value!="REVIEWED" or not payload.edge_reference or not payload.affected_profiles or not expiry or not datetime.now(timezone.utc)<expiry<=datetime.now(timezone.utc)+timedelta(days=30):raise HTTPException(422,detail="A routing effect needs reviewed status, a mapped edge, affected profiles and a future expiry within 30 days.")
        report=report_detail(identity)
        if state["graph"] is None:
            raise HTTPException(503,detail="The walking network is still starting. Retry before applying a routing effect.")
        try:
            parts=json.loads(payload.edge_reference)
            if not isinstance(parts,list) or len(parts)!=3:raise ValueError()
            def node(value):return int(value) if str(value).isdigit() else str(value)
            u,v,key=map(node,parts); graph=state["graph"]
            attrs=graph.get_edge_data(u,v,key)
            if not attrs:raise ValueError()
            from .groundtruth import _project
            from shapely.geometry import LineString
            if _project(LineString(_edge_coords(graph,u,v,attrs))).distance(_project(Point(report["longitude"],report["latitude"])))>35:raise ValueError()
            if report["category"] in {"curb_ramp_present","missing_tactile_paving"} and payload.routing_effect=="block":raise ValueError()
            reference=json.dumps([str(u),str(v),str(key)],separators=(",",":"))
        except Exception as exc:raise HTTPException(422,detail="The routing effect must reference an applicable mapped pedestrian edge within 35 metres of this report.") from exc
    try:return review_observation(identity,status=payload.status.value,reviewer=payload.reviewer,reason=payload.reason,edge_reference=reference,routing_effect=payload.routing_effect,effective_until=expiry.isoformat() if expiry else None,affected_profiles=payload.affected_profiles)
    except LookupError as exc:raise HTTPException(404,detail=str(exc)) from exc
    except Exception as exc:raise HTTPException(503,detail="Community report storage is unavailable.") from exc


def calculate_route(graph, origin, destination_node, algorithm, profile, stop, **kwargs):
    """Route to the best recorded arrival point for the stop (entrance or stop)."""
    if "report_effects" not in kwargs:
        database_started, database_cpu_started = time.perf_counter(), time.process_time()
        try:
            kwargs["report_effects"] = _routing_effects()
        except Exception as exc:
            context = ACTIVE_REQUEST_CONTEXT.get() or {}
            _runtime_event("routing_effects_read_failed", request_id=context.get("request_id"),
                           error_type=type(exc).__name__,
                           wall_seconds=round(time.perf_counter()-database_started,4),
                           process_cpu_seconds=round(time.process_time()-database_cpu_started,4))
            raise
        else:
            context = ACTIVE_REQUEST_CONTEXT.get() or {}
            _runtime_event("routing_effects_read_complete", request_id=context.get("request_id"),
                           wall_seconds=round(time.perf_counter()-database_started,4),
                           process_cpu_seconds=round(time.process_time()-database_cpu_started,4))
    targets = _arrival_targets(stop, profile)
    if len(targets) == 1 and targets[0][2]["type"] == "stop":
        targets = [(destination_node, targets[0][1], targets[0][2])]
    best = None
    failure = None
    for node, target_stop, arrival in targets:
        try:
            result = _calculate_single(graph, origin, node, algorithm, profile, target_stop, **kwargs)
        except (LookupError, ValueError) as exc:
            failure = exc
            continue
        score = (
            (result["optimization_hops"], result["optimization_cost_m"], result["distance_m"])
            if algorithm == Algorithm.breadth_first
            else (result["optimization_cost_m"], result["distance_m"])
        )
        if best is None or score < best[2]:
            best = (result, arrival, score)
    if best is None:
        raise failure or LookupError("No walking route connects this starting point to the selected stop.")
    result, arrival, _ = best
    result["destination"] = {
        key: stop[key] for key in ("stop_id", "stop_name", "latitude", "longitude", "agency", "agency_name",
                                    "station_name", "platform_name") if key in stop
    }
    result["arrival"] = arrival
    result["arrival_options_considered"] = len(targets)
    return result


def _routing_effects():
    effects={}
    durability=database_durability()
    if durability == "postgresql" or (state.get("observations_ready") and durability == "filesystem-persistent"):
        try:
            effects=active_routing_effects()
            state["observations_ready"]=True
        except Exception as exc:raise HTTPException(503,detail="Reviewed report information is unavailable. Please retry before routing.") from exc
    return effects


def _calculate_single(*args,report_effects=None,**kwargs):
    effects = _routing_effects() if report_effects is None else report_effects
    result=base_calculate_route(*args,**kwargs,report_effects=effects)
    result["reviewed_report_effects"]=list(effects.values())
    result["profile_assumptions"]=configuration().get(result["profile"],{})
    if args[4] != Profile.standard:
        baseline=base_calculate_route(args[0],args[1],args[2],args[3],Profile.standard,args[5],report_effects=effects)
        result["same_mapped_route_as_standard"]=baseline["selected_edges"]==result["selected_edges"]
        if result["same_mapped_route_as_standard"]:
            result["profile_explanation"]="This profile and standard walking use the same mapped route under the recorded attributes. Accessibility information is incomplete, so this does not confirm suitability for every user."
    return result


@app.get("/stops")
def stops():
    _ready()
    all_stops = state.get("transit_stops") or state["stops"]
    return {
        "stops": [_public_stop(stop) for stop in all_stops],
        "count": len(all_stops),
        "sources": state.get("transit_sources", {}),
    }


@app.post("/route")
async def route(payload: RouteRequest):
    # A real trip may be the very first request to a newly started serverless
    # worker. Join the shared county initialization task instead of making the
    # user receive an immediate 503 while the map and stop search are already
    # available. The same bounded wait is used by the explicit warmup endpoint.
    initialization = getattr(app.state, "initialization", None)
    if state["graph"] is None and initialization is not None and not initialization.done():
        try:
            await asyncio.wait_for(asyncio.shield(initialization), INITIALIZATION_REQUEST_SECONDS)
        except TimeoutError:
            pass
    graph, stop = _route_inputs(
        payload.origin_latitude, payload.origin_longitude, payload.destination_stop_id
    )
    try:
        result = calculate_route(
            graph,
            (payload.origin_latitude, payload.origin_longitude),
            stop["graph_node"],
            payload.algorithm,
            payload.profile,
            stop,
        )
        index = state.get("groundtruth")
        result["groundtruth_evidence"] = (
            index.route_evidence(result["geometry"])
            if index
            else {
                "status": "unavailable",
                "nearby_feature_count": None,
                "features": [],
                "message": "Municipal sidewalk comparison is unavailable.",
            }
        )
        return result
    except LookupError as exc:
        logger.info(
            "Route unavailable for requested destination and profile %s",
            payload.profile.value,
        )
        raise HTTPException(422, detail=str(exc)) from exc
    except ValueError as exc:
        logger.warning("Routing rejected invalid graph cost or configuration: %s", exc)
        raise HTTPException(422, detail=str(exc)) from exc


def _route_inputs(latitude: float, longitude: float, stop_id: str):
    _ready()
    if not _inside(latitude, longitude):
        area = (
            "Santa Clara County"
            if state.get("region") == COUNTY_REGION
            else f"the {state['radius_m']} m Diridon Station study area"
        )
        raise HTTPException(
            422, detail=f"Starting point is outside the supported area ({area})."
        )
    stop = next(
        (candidate for candidate in (state.get("transit_stops") or state["stops"]) if candidate["stop_id"] == stop_id),
        None,
    )
    if stop is None:
        raise HTTPException(
            404,
            detail="The selected destination is not in the loaded transit stop data.",
        )
    return state["graph"], stop


@app.post("/route/compare")
def compare_routes(payload: RouteComparisonRequest):
    """Run all supported routing objectives against the same loaded graph."""
    graph, stop = _route_inputs(
        payload.origin_latitude, payload.origin_longitude, payload.destination_stop_id
    )
    results = []
    for profile in Profile:
        try:
            result = calculate_route(
                graph,
                (payload.origin_latitude, payload.origin_longitude),
                stop["graph_node"],
                payload.algorithm,
                profile,
                stop,
            )
            index = state.get("groundtruth")
            result["groundtruth_evidence"] = (
                index.route_evidence(result["geometry"])
                if index
                else {
                    "status": "unavailable",
                    "nearby_feature_count": None,
                    "features": [],
                    "message": "Municipal sidewalk comparison is unavailable.",
                }
            )
            results.append(
                {
                    "profile": profile.value,
                    "objective": PROFILE_OBJECTIVES[profile],
                    "available": True,
                    "route": result,
                    "error": None,
                }
            )
        except (LookupError, ValueError) as exc:
            results.append(
                {
                    "profile": profile.value,
                    "objective": PROFILE_OBJECTIVES[profile],
                    "available": False,
                    "route": None,
                    "error": str(exc),
                }
            )
    return {
        "algorithm": payload.algorithm.value,
        "origin": {
            "latitude": payload.origin_latitude,
            "longitude": payload.origin_longitude,
        },
        "destination": {
            key: stop[key] for key in ("stop_id", "stop_name", "latitude", "longitude", "agency", "agency_name") if key in stop
        },
        "results": results,
    }


@app.get("/gaps")
def stop_gaps(limit: int = Query(10, ge=1, le=100)):
    _ready()
    return state["gaps"].summary(limit)


@app.get("/stops/{stop_id}/access")
def stop_access(stop_id: str):
    _ready()
    try:
        return state["gaps"].detail(stop_id)
    except KeyError as exc:
        raise HTTPException(404, detail="VTA stop not found") from exc


@app.get("/stops/{stop_id}")
def stop_detail(stop_id: str):
    _ready()
    all_stops = state.get("transit_stops") or state["stops"]
    stop = next((s for s in all_stops if s["stop_id"] == stop_id), None)
    if stop is None:
        raise HTTPException(404, detail="Transit stop not found")
    agency = stop.get("agency")
    agency_schedules = state.get("agency_schedules", {})
    schedule = agency_schedules.get(agency) if agency in agency_schedules else state.get("schedule")
    source_stop_id = stop.get("source_stop_id", stop_id)
    return {
        **_public_stop(stop),
        "agency": stop.get("agency_name", "VTA"),
        "agency_url": AGENCIES.get(agency, {}).get("developer_url", "https://www.vta.org/go/developers"),
        "schedule_url": AGENCIES.get(agency, {}).get("schedule_url", "https://www.vta.org/go/schedules"),
        "service": schedule.details(source_stop_id) if schedule else None,
    }


@app.post("/compare")
def mobility_comparison(payload: RouteComparisonRequest):
    graph, stop = _route_inputs(
        payload.origin_latitude, payload.origin_longitude, payload.destination_stop_id
    )
    # Fix the same distance-optimal algorithm for a fair profile comparison.
    from .models import Algorithm

    origin = (payload.origin_latitude, payload.origin_longitude)
    standard = calculate_route(
        graph, origin, stop["graph_node"], Algorithm.astar, Profile.standard, stop
    )
    try:
        alternative = calculate_route(
            graph, origin, stop["graph_node"], Algorithm.astar, payload.profile, stop
        )
    except (LookupError, ValueError) as exc:
        return {
            "standard": standard,
            "alternative": None,
            "extra_distance_m": None,
            "extra_minutes": None,
            "ratio": None,
            "unavailable_reason": str(exc),
        }
    base, alt = standard["distance_m"], alternative["distance_m"]
    return {
        "standard": standard,
        "alternative": alternative,
        "extra_distance_m": round(alt - base, 1),
        "extra_minutes": round(
            (alternative["duration_seconds"] - standard["duration_seconds"]) / 60, 2
        ),
        "ratio": round(alt / base, 3) if base else None,
        "same_mapped_route":standard["selected_edges"]==alternative["selected_edges"],
        "explanation":("Both profiles use the same mapped route under the recorded attributes and model assumptions. Missing accessibility information does not confirm suitability for every user." if standard["selected_edges"]==alternative["selected_edges"] else "The selected mobility rules choose different mapped edges. Additional time also reflects the profile's assumed speed."),
        "assumptions": {
            "standard_speed_mps": 1.2,
            "profile_speed_mps": SPEED_MPS[payload.profile.value],
            "interpretation": "Estimated time difference includes the different assumed speeds. Costs reflect documented tags, not field verification.",
        },
    }


@app.post("/algorithms/compare")
def algorithm_comparison(payload: RouteRequest):
    from .models import Algorithm

    graph, stop = _route_inputs(
        payload.origin_latitude, payload.origin_longitude, payload.destination_stop_id
    )
    results = []
    for algorithm in Algorithm:
        try:
            result = calculate_route(
                graph,
                (payload.origin_latitude, payload.origin_longitude),
                stop["graph_node"],
                algorithm,
                payload.profile,
                stop,
            )
            results.append(
                {
                    k: result[k]
                    for k in (
                        "algorithm",
                        "distance_m",
                        "computation_time_ms",
                        "optimization_cost_m",
                        "optimization_hops",
                        "algorithm_warning",
                    )
                }
            )
        except (ValueError, LookupError) as exc:
            results.append({"algorithm": algorithm.value, "error": str(exc)})
    return {
        "results": results,
        "note": "Wall-clock timings include search and geometry reconstruction. Hops count the chosen path, not all expanded nodes. BFS minimizes hops; the other algorithms minimize profile-weighted cost.",
    }


@app.get("/letters/{stop_id}", response_class=PlainTextResponse)
def civic_letter(stop_id: str):
    from .letters import generate_letter
    return generate_letter(stop_access(stop_id))


from pydantic import BaseModel, Field


class AddressSearch(BaseModel):
    query: str = Field(min_length=3, max_length=200)


@app.post("/geocode")
def geocode(payload: AddressSearch):
    from .geocoding import search
    from shapely.geometry import Point

    boundary = (
        load_county_boundary()
        if state.get("region") == COUNTY_REGION
        else Point(CENTER[1], CENTER[0]).buffer(state["radius_m"] / 111320)
    )
    try:
        return search(payload.query, boundary)
    except RuntimeError as exc:
        raise HTTPException(429, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    except Exception as exc:
        logger.warning("Address provider unavailable: %s", type(exc).__name__)
        raise HTTPException(
            503, detail="Address search is unavailable. Choose on the map instead."
        ) from exc


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
