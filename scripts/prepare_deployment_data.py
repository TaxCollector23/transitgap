"""Fetch real OSM and VTA data into the bundle before a Vercel deployment."""
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
os.environ["TRANSITGAP_DATA_DIR"] = str(root / "backend" / "data")
from backend.app.data_loader import initialize

graph, stops = initialize()
print(f"Prepared OSM graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges")
print(f"Prepared official VTA stops connected to the graph: {len(stops)}")
