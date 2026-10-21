"""Run with the database OWNER URL; never place that credential in the frontend."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.app.observations import initialize_observations
initialize_observations()
print('Report migrations completed; verify runtime permissions before enabling writes.')
