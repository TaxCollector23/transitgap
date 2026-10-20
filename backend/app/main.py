from __future__ import annotations
import math, os
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from .data_loader import CENTER, DEFAULT_RADIUS_M, DatasetError, initialize
from .models import RouteRequest
from .routing import calculate_route

state = {"graph": None, "stops": [], "error": None, "radius_m": DEFAULT_RADIUS_M}

def _load() -> None:
    try:
        graph, stops = initialize()
        state.update(graph=graph, stops=stops, error=None, radius_m=int(os.getenv("TRANSITGAP_RADIUS_M",DEFAULT_RADIUS_M)))
    except Exception as exc:
        state.update(graph=None, stops=[], error=str(exc))

@asynccontextmanager
async def lifespan(app: FastAPI):
    pool=ThreadPoolExecutor(max_workers=1)
    await __import__("asyncio").get_running_loop().run_in_executor(pool,_load)
    yield
    pool.shutdown(wait=False)

app=FastAPI(title="TransitGap API",version="0.1.0",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=os.getenv("CORS_ORIGINS","http://localhost:5173,http://127.0.0.1:5173").split(","),allow_credentials=False,allow_methods=["GET","POST"],allow_headers=["*"])

def _ready():
    if state["graph"] is None or not state["stops"]:
        raise HTTPException(status_code=503,detail={"message":"TransitGap data is not ready.","initialization_error":state["error"] or "Dataset initialization is still in progress."})

def _inside(lat:float,lon:float)->bool:
    lat0,lon0=CENTER; dlat=math.radians(lat-lat0); dlon=math.radians(lon-lon0)
    a=math.sin(dlat/2)**2+math.cos(math.radians(lat0))*math.cos(math.radians(lat))*math.sin(dlon/2)**2
    return 6371000*2*math.asin(math.sqrt(a)) <= state["radius_m"]

@app.get("/health")
def health():
    return {"ready":state["graph"] is not None and bool(state["stops"]),"datasets":{"osm_walk_graph":"ready" if state["graph"] is not None else "unavailable","vta_gtfs_stops":"ready" if state["stops"] else "unavailable"},"error":state["error"]}

@app.get("/coverage")
def coverage():
    return {"center":{"latitude":CENTER[0],"longitude":CENTER[1]},"radius_m":state["radius_m"],"description":"Circular supported area around San Jose Diridon Station"}

@app.get("/stops")
def stops():
    _ready()
    return {"stops":[{k:v for k,v in stop.items() if k!="graph_node" and k!="connector_distance_m"} for stop in state["stops"]],"count":len(state["stops"])}

@app.post("/route")
def route(payload:RouteRequest):
    _ready()
    if not _inside(payload.origin_latitude,payload.origin_longitude):
        raise HTTPException(422,detail=f"Starting point is outside the supported {state['radius_m']} m area around Diridon Station.")
    stop=next((s for s in state["stops"] if s["stop_id"]==payload.destination_stop_id),None)
    if stop is None: raise HTTPException(404,detail="The selected destination is not in the loaded VTA stop dataset.")
    try:
        result=calculate_route(state["graph"],(payload.origin_latitude,payload.origin_longitude),stop["graph_node"],payload.algorithm,payload.profile,stop)
    except LookupError as exc: raise HTTPException(422,detail=str(exc)) from exc
    except ValueError as exc: raise HTTPException(422,detail=str(exc)) from exc
    return {**result,"destination":{"stop_id":stop["stop_id"],"stop_name":stop["stop_name"],"latitude":stop["latitude"],"longitude":stop["longitude"]}}

# Vercel builds the React app before importing this ASGI app. In local development,
# Vite serves the frontend separately and this mount is available after a production build.
_frontend = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _frontend.exists():
    app.mount("/", StaticFiles(directory=_frontend, html=True), name="frontend")
